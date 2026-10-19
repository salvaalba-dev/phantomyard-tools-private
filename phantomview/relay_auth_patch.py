"""Patch the pinned nostr-tools AUTH race in a disposable native build only.

Run after the upstream frozen-lockfile installation. No installation, service or
socket operation is performed. The original lockfile and package stay unchanged;
the returned manifest records every exact dependency file changed by the overlay.
"""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

VERSION = '2.23.3'
# npm tarball integrity matches the pinned upstream bun.lock.
EXPECTED_INPUTS = {'lib/esm/abstract-pool.js': '195176402cd13a6dfeeaccf6aaa14db6e1a31ccd153bba89a6250b68683aa58c', 'lib/esm/abstract-relay.js': '840d7880ecb1918eed1e4d87d48db0f23b24ca436543506d6b3eec74e95f7926', 'lib/esm/index.js': '408eeceb510b1aa3bb995253ebcb299763717ca193b3488e0ff90be936bb72ae', 'lib/esm/nip46.js': '6d387447c2010f3d14e06f92ad4f1e5552cbe4a1e1bb9f92737e405c1a623e9b', 'lib/esm/pool.js': 'e745566488bb74884cb78bcbc61cfbaeeec9c3a3ae601275ea752c87deffb6af', 'lib/esm/relay.js': '59f02beef9bd8a33be5d1c124e132013d71b31f52df2206d3e06b081b005c013', 'lib/cjs/abstract-pool.js': 'c9960829c3ec29d37f1c81ae5d3616976ace13e507a700922990b2913cf3e74a', 'lib/cjs/abstract-relay.js': '71e5376011b0caeddac099356ef3b6d52003fdc7cc882ce922e63d45b2272947', 'lib/cjs/index.js': 'd2ef638184edbc02b1e7954e82b45fca7057efc87393632d6e80ca6ffa1902ed', 'lib/cjs/nip46.js': '24837ecbb09b6631220074f5cd82682bbd97bd79a38457dfa2d3c209b9c164f0', 'lib/cjs/pool.js': '50b6e121582f78781adf792ffc6fc3c8689c4a2df688a82bf47a75674b142144', 'lib/cjs/relay.js': 'dd042b7ab9aef03ee122bffce85f1fc9a688b4f5ca4f1441cd5b0f420a19d689'}
OLD_SEND = '''  async send(message) {
    if (!this.connectionPromise)
      throw new SendingOnClosedConnection(message, this.url);
    this.connectionPromise.then(() => {
      this.ws?.send(message);
    });
  }'''
NEW_SEND = OLD_SEND.replace('    this.connectionPromise.then(', '    return this.connectionPromise.then(')
OLD_AUTH = '''  async auth(signAuthEvent) {
    const challenge = this.challenge;
    if (!challenge)
      throw new Error("can't perform auth, no challenge was received");
    if (this.authPromise)
      return this.authPromise;
    this.authPromise = new Promise(async (resolve, reject) => {
      try {
        let evt = await signAuthEvent(makeAuthEvent(this.url, challenge));
        let timeout = setTimeout(() => {
          let ep = this.openEventPublishes.get(evt.id);
          if (ep) {
            ep.reject(new Error("auth timed out"));
            this.openEventPublishes.delete(evt.id);
          }
        }, this.publishTimeout);
        this.openEventPublishes.set(evt.id, { resolve, reject, timeout });
        this.send('["AUTH",' + JSON.stringify(evt) + "]");
      } catch (err) {
        console.warn("subscribe auth function failed:", err);
      }
    });
    return this.authPromise;
  }'''
NEW_AUTH = '''  async auth(signAuthEvent) {
    const challenge = this.challenge;
    if (!challenge)
      throw new Error("can't perform auth, no challenge was received");
    if (this.authPromise)
      return this.authPromise;
    this.authPromise = new Promise((resolve, reject) => {
      const signAndSend = async () => {
        const evt = await signAuthEvent(makeAuthEvent(this.url, challenge));
        const timeout = setTimeout(() => {
          const ep = this.openEventPublishes.get(evt.id);
          if (ep) {
            ep.reject(new Error("auth timed out"));
            this.openEventPublishes.delete(evt.id);
          }
        }, this.publishTimeout);
        this.openEventPublishes.set(evt.id, { resolve, reject, timeout });
        try {
          await this.send('["AUTH",' + JSON.stringify(evt) + "]");
        } catch (err) {
          const ep = this.openEventPublishes.get(evt.id);
          if (ep) {
            clearTimeout(ep.timeout);
            this.openEventPublishes.delete(evt.id);
          }
          throw err;
        }
      };
      void signAndSend().catch(reject);
    });
    return this.authPromise;
  }'''


def transform(text):
    """Fail closed on drift or an already patched input; validate before writes."""
    if text.count(OLD_SEND) != 1 or text.count(OLD_AUTH) != 1:
        raise ValueError('Reviewed nostr-tools send/auth methods changed')
    return text.replace(OLD_SEND, NEW_SEND).replace(OLD_AUTH, NEW_AUTH)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def patch(root):
    root = Path(root).resolve(strict=True)
    package = root / 'node_modules/nostr-tools'
    if package.is_symlink() or not package.resolve(strict=True).is_relative_to(root):
        raise ValueError('Use the disposable build dependency directory')
    metadata = json.loads((package / 'package.json').read_text(encoding='utf-8'))
    if metadata.get('name') != 'nostr-tools' or metadata.get('version') != VERSION:
        raise ValueError('Only the reviewed nostr-tools version is supported')
    # Each entry point contains its own bundled AbstractRelay. Patching only
    # abstract-relay.js would leave the daemon's SimplePool copy vulnerable.
    plan = []
    for directory in ('lib/esm', 'lib/cjs'):
        for path in sorted((package / directory).glob('*.js')):
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(package):
                raise ValueError('Linked dependency entry point')
            raw = path.read_bytes()
            text = raw.decode('utf-8')
            if '  async auth(signAuthEvent) {' in text:
                fixed = transform(text).encode('utf-8')
                plan.append((path, fixed, {'path': path.relative_to(package).as_posix(),
                    'before_sha256': digest(raw), 'after_sha256': digest(fixed)}))
    actual = {row['path']: row['before_sha256'] for _, _, row in plan}
    if actual != EXPECTED_INPUTS:
        raise ValueError('Dependency entry points differ from reviewed npm bytes')
    for path, fixed, _ in plan:
        # Bun/pnpm may hard-link dependencies to a shared content cache. Replace
        # the build's directory entry; never truncate the shared inode in place.
        fd, temporary = tempfile.mkstemp(prefix='.phantomview-auth-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(fixed)
            os.chmod(temporary, path.stat().st_mode & 0o777)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {'schema_version': 1, 'package': 'nostr-tools', 'version': VERSION,
            'patch_sha256': digest(Path(__file__).read_bytes()),
            'files': [row for _, _, row in plan], 'installed': False,
            'activation_ready': False}


def verify_manifest(root, manifest):
    package = Path(root).resolve(strict=True) / 'node_modules/nostr-tools'
    if (manifest.get('schema_version') != 1 or manifest.get('package') != 'nostr-tools'
            or manifest.get('version') != VERSION
            or manifest.get('patch_sha256') != digest(Path(__file__).read_bytes())
            or manifest.get('installed') is not False
            or manifest.get('activation_ready') is not False):
        raise ValueError('Dependency patch provenance is invalid')
    rows = manifest.get('files', [])
    if (len(rows) != len(EXPECTED_INPUTS)
            or {row['path']: row['before_sha256'] for row in rows} != EXPECTED_INPUTS):
        raise ValueError('Dependency patch member set differs from reviewed inputs')
    for row in rows:
        path = package / row['path']
        if (path.is_symlink() or not path.resolve(strict=True).is_relative_to(package)
                or digest(path.read_bytes()) != row['after_sha256']):
            raise ValueError('Patched dependency changed before compilation or receipt')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Disposable native source checkout')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    output = Path(args.manifest)
    if args.verify:
        verify_manifest(args.source, json.loads(output.read_text(encoding='utf-8')))
        return
    if output.exists() or output.is_symlink():
        parser.error('Refusing to overwrite patch provenance')
    result = patch(args.source)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()

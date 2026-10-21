# Persona tool file references

The existing persona card shows declared tools and their implementation files in
two columns. Its layout, contact pane and document reader remain unchanged.

An installation manifest may include explicit file bindings:

```json
{
  "persona_tool_files": [
    {"actor": "example:actors:coordinator", "tool": "email", "files": ["tools/mail.py"]}
  ]
}
```

Bindings must name a selected persona and one of its declared, non-excluded tools.
Files are bounded relative paths under that persona's `tools/` directory. A shared
script may be referenced by several tools. The collector checks metadata only:
regular file, symbolic link, missing or unavailable. It never follows symbolic
links, reads script contents, imports scripts or executes commands.

The existing reviewed profile export carries these references only when
`profile_fields` is enabled. They remain part of the persona record and require
the same explicit projection review and category/scope approval as its metadata.
The browser receives only references included in its authorized persona record.
There are no direct filesystem links, executable buttons or new API routes.
Changing references or observed file states changes the source fingerprint;
publication must be refreshed through the existing review procedure.

Unmapped tools show `No file binding published`. A declaration or file-presence
observation does not prove that the tool is operational. Secrets, command arguments,
absolute paths and arbitrary configuration bodies are not exported.

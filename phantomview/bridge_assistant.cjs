'use strict';
// Optional PhantomBridge middleware. A separate token grants only this namespace.
const fs=require('node:fs'),http=require('node:http'),crypto=require('node:crypto');
const PREFIX='/phantomview-assistant';
function createHandler(configFile){
 let cfg,token;
 try{
  cfg=JSON.parse(fs.readFileSync(configFile,'utf8'));
  if(!Number.isInteger(cfg.worker_port)||cfg.worker_port<1024||cfg.worker_port>65535)throw Error();
  if(fs.lstatSync(cfg.token_file).isSymbolicLink())throw Error();
  token=fs.readFileSync(cfg.token_file,'utf8').trim();if(!/^[a-f0-9]{64}$/.test(token))throw Error();
 }catch{cfg=null;}
 const send=(res,status,body)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(body));};
 return function handle(req,res){
  const path=(req.url||'').split('?')[0];if(path!==PREFIX&&!path.startsWith(PREFIX+'/'))return false;
  if(!cfg){send(res,503,{error:'Assistant is not configured'});return true;}
  const supplied=String(req.headers.authorization||'').replace(/^Bearer /,'');
  if(!['127.0.0.1','::1','::ffff:127.0.0.1'].includes(req.socket.remoteAddress)||supplied.length!==token.length||!crypto.timingSafeEqual(Buffer.from(supplied),Buffer.from(token))){send(res,401,{error:'Assistant authentication required'});return true;}
  if(req.url.includes('?')||req.url.includes('#')){send(res,400,{error:'Query strings are not accepted'});return true;}
  const target=path.slice(PREFIX.length),method=req.method;
  const valid=method==='GET'&&target==='/status'||method==='POST'&&target==='/jobs'||['GET','DELETE'].includes(method)&&/^\/jobs\/[a-f0-9-]{36}$/.test(target);
  if(!valid){send(res,404,{error:'Unknown assistant operation'});return true;}
  const owner=String(req.headers['x-phantomview-session']||'');
  if(target!=='/status'&&!/^[a-f0-9]{64}$/.test(owner)){send(res,400,{error:'Session boundary required'});return true;}
  let body=[],size=0,over=false;
  req.on('data',chunk=>{size+=chunk.length;if(size>16000){if(!over)send(res,413,{error:'Assistant request too large'});over=true;}else body.push(chunk);});
  req.on('end',()=>{
   if(over)return;
   const raw=Buffer.concat(body);
   const upstream=http.request({hostname:'127.0.0.1',port:cfg.worker_port,path:target,method,headers:{Authorization:'Bearer '+token,'X-PhantomView-Session':owner,'Content-Type':'application/json','Content-Length':raw.length},timeout:3000},reply=>{
    let parts=[],bytes=0;
    reply.on('data',chunk=>{bytes+=chunk.length;if(bytes>65536){upstream.destroy();}else parts.push(chunk);});
    reply.on('end',()=>{if(res.writableEnded)return;if(bytes>65536)return send(res,502,{error:'Assistant response too large'});res.writeHead(reply.statusCode,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(Buffer.concat(parts));});
   });
   upstream.on('timeout',()=>upstream.destroy());
   upstream.on('error',()=>{if(!res.writableEnded)send(res,503,{error:'Assistant worker unavailable'});});
   upstream.end(raw);
  });
  req.on('error',()=>{if(!res.writableEnded)send(res,400,{error:'Assistant request interrupted'});});
  return true;
 };
}
module.exports={createHandler};
// Run an isolated loopback adapter without modifying an existing bridge service.
if(require.main===module){
 const [configFile,portText]=process.argv.slice(2),port=Number(portText);
 if(!configFile||!Number.isInteger(port)||port<1024||port>65535)throw Error('Explicit loopback configuration required');
 const handle=createHandler(configFile);
 http.createServer((req,res)=>{if(!handle(req,res)){res.writeHead(404);res.end();}}).listen(port,'127.0.0.1');
}

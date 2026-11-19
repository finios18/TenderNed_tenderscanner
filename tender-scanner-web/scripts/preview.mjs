// Lokale viewer van de statische build; geen applicatiebackend.
import { createServer } from "node:http";
import { readFile,stat } from "node:fs/promises";
import { extname,resolve,sep } from "node:path";
const root=resolve("out");
const mime={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".css":"text/css; charset=utf-8",".json":"application/json",".svg":"image/svg+xml",".txt":"text/plain; charset=utf-8",".png":"image/png",".ico":"image/x-icon"};
const server=createServer(async(req,res)=>{
  try{
    const pathname=decodeURIComponent(new URL(req.url??"/","http://127.0.0.1").pathname);
    let file=resolve(root,"."+pathname);
    if(file!==root&&!file.startsWith(root+sep)){res.writeHead(403);res.end();return;}
    if((await stat(file)).isDirectory())file=resolve(file,"index.html");
    const data=await readFile(file);res.writeHead(200,{"Content-Type":mime[extname(file)]??"application/octet-stream","X-Content-Type-Options":"nosniff","Cache-Control":"no-store"});res.end(data);
  }catch{res.writeHead(404,{"Content-Type":"text/plain; charset=utf-8"});res.end("Pagina niet gevonden");}
});
server.listen(3000,"127.0.0.1",()=>console.log("Local: http://127.0.0.1:3000"));

"""Generate and compile the bounded Metal helper on macOS. No wallet access."""
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gpu_miner import SOURCE

source=SOURCE.replace('__constant','constant').replace('uint *s','thread uint *s').replace('uint *w','thread uint *w')
source=source.replace('__kernel void hash_headers(__global const uchar *prefix,uint start,__global uchar *out){\n uint id=get_global_id(0),nonce=start+id,w[64],s[8];init(s);',
    'kernel void hash_headers(device const uchar *prefix [[buffer(0)]], constant uint &start [[buffer(1)]], device uchar *out [[buffer(2)]], uint id [[thread_position_in_grid]]){\n uint nonce=start+id,w[64],s[8];init(s);')
source='#include <metal_stdlib>\nusing namespace metal;\n'+source
swift=r'''
import Foundation
import Metal
func output(_ value:[String:Any]) { let data=try! JSONSerialization.data(withJSONObject:value,options:[.sortedKeys]);print(String(data:data,encoding:.utf8)!);fflush(stdout) }
if CommandLine.arguments.contains("--telemetry") {
 output(["name":"Apple Metal GPU", "thermal_state":ProcessInfo.processInfo.thermalState.rawValue]);exit(0)
}
guard let device=MTLCreateSystemDefaultDevice(),let queue=device.makeCommandQueue() else {output(["error":"No Metal GPU available"]);exit(1)}
let source=METAL_SOURCE
do {
 let library=try device.makeLibrary(source:source,options:nil)
 guard let function=library.makeFunction(name:"hash_headers") else {exit(1)}
 let pipeline=try device.makeComputePipelineState(function:function)
 output(["ready":true,"name":device.name])
 while let line=readLine() {
  guard let data=line.data(using:.utf8),let job=try JSONSerialization.jsonObject(with:data) as? [String:Any],let hex=job["prefix"] as? String,let number=job["start"] as? UInt64,let count=job["count"] as? Int,hex.count==152,count>0,count<=32768,number+UInt64(count)<=4294967296 else {output(["error":"Invalid bounded job"]);continue}
  if ProcessInfo.processInfo.thermalState != .nominal {output(["error":"Apple thermal state elevated; stopped"]);continue}
  var bytes=[UInt8]();var index=hex.startIndex
  while index<hex.endIndex {let end=hex.index(index,offsetBy:2);guard let b=UInt8(hex[index..<end],radix:16) else {exit(1)};bytes.append(b);index=end}
  guard let input=device.makeBuffer(bytes:bytes,length:76,options:.storageModeShared),let result=device.makeBuffer(length:count*32,options:.storageModeShared),let command=queue.makeCommandBuffer(),let encoder=command.makeComputeCommandEncoder() else {exit(1)}
  var start=UInt32(number)
  encoder.setComputePipelineState(pipeline);encoder.setBuffer(input,offset:0,index:0);encoder.setBytes(&start,length:4,index:1);encoder.setBuffer(result,offset:0,index:2)
  encoder.dispatchThreads(MTLSize(width:count,height:1,depth:1),threadsPerThreadgroup:MTLSize(width:min(64,pipeline.maxTotalThreadsPerThreadgroup),height:1,depth:1));encoder.endEncoding();command.commit();command.waitUntilCompleted()
  guard command.status == .completed else {output(["error":"Metal command failed"]);continue}
  let raw=UnsafeBufferPointer(start:result.contents().assumingMemoryBound(to:UInt8.self),count:count*32)
  output(["hashes":raw.map{String(format:"%02x",$0)}.joined()])
 }
} catch {output(["error":String(describing:error)]);exit(1)}
'''.replace('METAL_SOURCE',json.dumps(source))
destination=Path(sys.argv[1]);destination.parent.mkdir(parents=True,exist_ok=True)
temporary=destination.with_suffix('.swift');temporary.write_text(swift,encoding='utf-8')
shader=destination.with_suffix('.metal');shader.write_text(source,encoding='utf-8')
subprocess.run(['xcrun','-sdk','macosx','metal','-c',str(shader),'-o',str(destination.with_suffix('.air'))],check=True)
subprocess.run(['xcrun','swiftc','-O','-framework','Metal','-framework','Foundation',str(temporary),'-o',str(destination)],check=True)

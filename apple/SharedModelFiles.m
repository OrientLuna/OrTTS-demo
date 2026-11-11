#import "SharedModelFiles.h"
#import <CommonCrypto/CommonDigest.h>
static NSString *Key(NSDictionary*e){return [NSString stringWithFormat:@"%@:%@",e[@"bytes"],e[@"sha256"]];}
BOOL OrTTSValidSharedAsset(NSURL *file,NSDictionary *entry){
 NSNumber *size=nil;if(![file getResourceValue:&size forKey:NSURLFileSizeKey error:nil]||size.unsignedLongLongValue!=[entry[@"bytes"]unsignedLongLongValue])return NO;
 NSInputStream*s=[NSInputStream inputStreamWithURL:file];[s open];CC_SHA256_CTX ctx;CC_SHA256_Init(&ctx);uint8_t buffer[65536];NSInteger n;while((n=[s read:buffer maxLength:sizeof(buffer)])>0)CC_SHA256_Update(&ctx,buffer,(CC_LONG)n);[s close];if(n<0)return NO;
 unsigned char hash[32];CC_SHA256_Final(hash,&ctx);NSMutableString*h=[NSMutableString new];for(int i=0;i<32;i++)[h appendFormat:@"%02x",hash[i]];return [h isEqual:entry[@"sha256"]];
}
NSDictionary *OrTTSSharedAssetIndex(NSArray<NSURL*>*roots){
 NSMutableDictionary*out=[NSMutableDictionary new];NSUInteger count=0;
 for(NSURL*root in roots){if(++count>64)break;@try{
  NSURL*meta=[root URLByAppendingPathComponent:@"download-manifest.json"];NSNumber*size=nil;[meta getResourceValue:&size forKey:NSURLFileSizeKey error:nil];if(!size||size.unsignedLongLongValue>2*1024*1024)continue;
  NSData*bytes=[NSData dataWithContentsOfURL:meta];NSDictionary*m=bytes?[NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil]:nil;NSArray*files=m[@"files"];if(![files isKindOfClass:NSArray.class]||files.count>256)continue;
  NSString*prefix=[root.URLByResolvingSymlinksInPath.path stringByAppendingString:@"/"];
  for(NSDictionary*entry in files){NSString*p=entry[@"path"],*hash=entry[@"sha256"];if(![p isKindOfClass:NSString.class]||[p hasPrefix:@"/"]||![hash isKindOfClass:NSString.class]||[hash rangeOfString:@"^[a-f0-9]{64}$" options:NSRegularExpressionSearch].location==NSNotFound)continue;NSURL*f=[root URLByAppendingPathComponent:p].URLByResolvingSymlinksInPath;if(![f.path hasPrefix:prefix])continue;NSString*k=Key(entry);if(!out[k])out[k]=[NSMutableArray new];[out[k]addObject:f];}
 }@catch(NSException*e){continue;}}
 return out;
}
BOOL OrTTSReuseSharedAsset(NSDictionary*index,NSDictionary*entry,NSURL*target,NSError**error){
 for(NSURL*source in index[Key(entry)]){if(!OrTTSValidSharedAsset(source,entry))continue;
  NSFileManager*fm=NSFileManager.defaultManager;if(![fm createDirectoryAtURL:target.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:error])return NO;
  NSURL*temp=[target.URLByDeletingLastPathComponent URLByAppendingPathComponent:[@".reuse-" stringByAppendingString:NSUUID.UUID.UUIDString]];
  if(![fm copyItemAtURL:source toURL:temp error:error])return NO;
  if(!OrTTSValidSharedAsset(temp,entry)){[fm removeItemAtURL:temp error:nil];if(error)*error=[NSError errorWithDomain:@"OrTTSReuse" code:1 userInfo:@{NSLocalizedDescriptionKey:@"本地复用文件校验失败"}];return NO;}
  BOOL ok;if([fm fileExistsAtPath:target.path])ok=[fm replaceItemAtURL:target withItemAtURL:temp backupItemName:nil options:0 resultingItemURL:nil error:error];else ok=[fm moveItemAtURL:temp toURL:target error:error];if(!ok)[fm removeItemAtURL:temp error:nil];return ok;
 }return NO;
}

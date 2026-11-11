#import "SharedModelFiles.h"
#import <CommonCrypto/CommonDigest.h>
static void check(BOOL ok){if(!ok)abort();}
int main(){@autoreleasepool{
 NSFileManager*fm=NSFileManager.defaultManager;NSURL*home=[NSURL fileURLWithPath:[NSTemporaryDirectory()stringByAppendingPathComponent:NSUUID.UUID.UUIDString]];NSURL*source=[home URLByAppendingPathComponent:@"old/a.bin"],*target=[home URLByAppendingPathComponent:@"new/renamed.bin"];
 [fm createDirectoryAtURL:source.URLByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];NSData*data=[@"shared weights"dataUsingEncoding:NSUTF8StringEncoding];[data writeToURL:source atomically:YES];unsigned char h[32];CC_SHA256(data.bytes,(CC_LONG)data.length,h);NSMutableString*sha=[NSMutableString new];for(int i=0;i<32;i++)[sha appendFormat:@"%02x",h[i]];
 NSDictionary*entry=@{@"path":@"a.bin",@"bytes":@(data.length),@"sha256":sha};[[NSJSONSerialization dataWithJSONObject:@{@"files":@[entry]} options:0 error:nil]writeToURL:[source.URLByDeletingLastPathComponent URLByAppendingPathComponent:@"download-manifest.json"]atomically:YES];
 NSDictionary*index=OrTTSSharedAssetIndex(@[source.URLByDeletingLastPathComponent]);NSError*e=nil;check(OrTTSReuseSharedAsset(index,entry,target,&e)&&!e&&OrTTSValidSharedAsset(target,entry));
 [[@"broken weights"dataUsingEncoding:NSUTF8StringEncoding]writeToURL:source atomically:NO];check(!OrTTSReuseSharedAsset(index,entry,[home URLByAppendingPathComponent:@"missing.bin"],&e));check(OrTTSValidSharedAsset(target,entry));
 [fm removeItemAtURL:home error:nil];NSLog(@"PASS: cross-version content reuse, renamed path, corruption rejection, independent copies");return 0;}}

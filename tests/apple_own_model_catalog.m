#import "OwnModelCatalog.h"
#import <CommonCrypto/CommonDigest.h>
static void check(BOOL ok, NSString *why){if(!ok){NSLog(@"FAIL: %@",why);exit(1);}}
static NSData *load(NSString *root,NSString *name){return [NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:name]];}
static NSDictionary *json(NSData *d){return [NSJSONSerialization JSONObjectWithData:d options:NSJSONReadingMutableContainers error:nil];}
static NSString *sha(NSData*d){unsigned char h[32];CC_SHA256(d.bytes,(CC_LONG)d.length,h);NSMutableString*s=[NSMutableString new];for(int i=0;i<32;i++)[s appendFormat:@"%02x",h[i]];return s;}
int main(int argc,char**argv){@autoreleasepool{
 NSString*root=argc>1?@(argv[1]):@"tests/fixtures/own-model-catalog";
 check(OrTTSOwnRepositories(json(load(root,@"owner.json"))).count==2,@"official namespace filter");
 NSArray*sources=OrTTSOwnManifestSources(@"OrientLuna/OrTTS-Qwen3-LFM-0.6B",json(load(root,@"files.json")));
 check(sources.count==2,@"root and nested manifests");
 NSMutableArray*models=[NSMutableArray new];
 for(NSInteger i=0;i<2;i++){NSData*d=load(root,i?@"ptq.json":@"q8.json");NSDictionary*m=OrTTSNormalizeOwnModel(sources[i],d);check(m!=nil,@"real manifest normalization");[models addObject:m];check(!OrTTSNormalizeOwnModel(sources[i],[d subdataWithRange:NSMakeRange(0,d.length-1)]),@"tamper rejection");}
 check([models[1][@"supported_variants"]isEqual:@[@"P3"]],@"PTQ P3 only");
 check(OrTTSMergeOwnCatalogs(@[models,models]).count==2,@"deduplication");
 for(NSString*bad in @[@"runtime",@"model_id",@"files"]){NSMutableDictionary*m=[json(load(root,@"ptq.json"))mutableCopy];if([bad isEqual:@"runtime"])m[bad]=@{@"schema":@"unknown"};else if([bad isEqual:@"model_id"])m[bad]=@"OtherOwner/OrTTS-Fake";else m[bad]=@[@{@"path":@"../escape",@"sha256":[@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0],@"bytes":@1}];NSData*d=[NSJSONSerialization dataWithJSONObject:m options:0 error:nil];NSMutableDictionary*s=[sources[1]mutableCopy];s[@"manifest_sha256"]=sha(d);check(!OrTTSNormalizeOwnModel(s,d),bad);}
 if(argc>2){NSError*e=nil;NSArray*live=OrTTSRefreshOwnCatalog(@[],&e);check(live.count>=3,e.localizedDescription?:@"live catalog");NSData*d=[NSJSONSerialization dataWithJSONObject:live options:NSJSONWritingPrettyPrinted error:nil];[d writeToFile:@(argv[2]) atomically:YES];NSLog(@"Live discovery: %lu models",(unsigned long)live.count);}
 NSLog(@"PASS: catalog discovery, nested PTQ, SHA, contract rejection and merge");return 0;}}

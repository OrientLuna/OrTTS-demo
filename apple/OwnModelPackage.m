#import "OwnModelPackage.h"
#import "OwnModelCatalog.h"
#import <CommonCrypto/CommonDigest.h>

NSDictionary *OrTTSOwnPackageInfo(NSInteger kind) {
    NSString *revision, *prefix, *hash, *directory;
    switch (kind) {
        case OrTTSOwnPackageQ8:
            revision=@"v0.3.1-preview"; prefix=@""; directory=@"models-liquid";
            hash=@"2b23c30f658e88ce8b3215e4ea24dacf8898ffca159a7908f61a8942e9e93720"; break;
        case OrTTSOwnPackageLegacy:
            revision=@"v0.2.0-preview"; prefix=@""; directory=@"models";
            hash=@"20e24b0bc7fd0e3b58e31dcb409c07102f9e0ddf33f8e70153f69073271b5f7f"; break;
        case OrTTSOwnPackagePTQ:
            revision=@"v0.3.1-ptq-q4"; prefix=@"variants/ptq-q4/"; directory=@"models-ptq-q4";
            hash=@"26cf9f79991fa38eb766541ee34a964c4521cb5130fd61034dad3302bebd0017"; break;
        default: return nil;
    }
    NSString *base=[NSString stringWithFormat:@"https://modelscope.cn/models/OrientLuna/OrTTS-Qwen3-LFM-0.6B/resolve/%@/%@",revision,prefix];
    NSString *name=kind==OrTTSOwnPackagePTQ?@"OrTTS 0.6B · PTQ Q4":kind==OrTTSOwnPackageLegacy?@"OrTTS 0.6B · 旧LFM":@"OrTTS 0.6B · 标准Q8";
    return @{@"id":@"OrientLuna/OrTTS-Qwen3-LFM-0.6B",@"name":[name stringByAppendingFormat:@" · %@",revision],@"revision":revision,@"manifest_url":[base stringByAppendingString:@"DOWNLOAD_MANIFEST.json"],@"manifest_sha256":hash,@"sha256":hash,@"directory":directory,@"p3_only":@(kind==OrTTSOwnPackagePTQ),@"supported_variants":kind==OrTTSOwnPackagePTQ?@[@"P3"]:@[@"P3",@"P5"],@"voices":kind==OrTTSOwnPackageLegacy?@[@"female",@"male"]:@[@"female",@"female_2",@"male",@"male_2"],@"decoder":kind==OrTTSOwnPackageLegacy?@"qwen_lfm":@"liquidcodec",@"source":@"builtin"};
}

NSDictionary *OrTTSVerifiedOwnModelManifest(NSData *data, NSDictionary *info) {
    if (!OrTTSValidOwnCatalogEntry(info) || !data.length || data.length>2*1024*1024) return nil;
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
    NSMutableString *hash=[NSMutableString new];
    for (NSUInteger i=0;i<sizeof(digest);i++) [hash appendFormat:@"%02x",digest[i]];
    if (![hash isEqual:info[@"manifest_sha256"]]) return nil;
    id document=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    if (![document isKindOfClass:NSDictionary.class] || ![document[@"revision"] isEqual:info[@"revision"]] || ![document[@"model_id"] isEqual:info[@"id"]] || ![document[@"schema"] isEqual:@"ortts-download-manifest-v1"]) return nil;
    return document;
}

BOOL OrTTSOwnPackageSupportsVariant(NSInteger kind, NSString *variant) {
    NSDictionary *info=OrTTSOwnPackageInfo(kind);
    return info && ([variant isEqual:@"P3"] || ([variant isEqual:@"P5"] && ![info[@"p3_only"] boolValue]));
}

NSDictionary *OrTTSVerifiedOwnManifest(NSData *data, NSInteger kind) { return OrTTSVerifiedOwnModelManifest(data,OrTTSOwnPackageInfo(kind)); }
NSArray *OrTTSBuiltInOwnModels(void) { return @[OrTTSOwnPackageInfo(0),OrTTSOwnPackageInfo(1),OrTTSOwnPackageInfo(2)]; }
NSString *OrTTSOwnModelDirectory(NSDictionary *entry) {
    if(!OrTTSValidOwnCatalogEntry(entry))return nil;
    for(NSDictionary *known in OrTTSBuiltInOwnModels())if([known[@"manifest_sha256"]isEqual:entry[@"manifest_sha256"]])return known[@"directory"];
    return [@"own-models/" stringByAppendingString:entry[@"manifest_sha256"]];
}
BOOL OrTTSOwnModelSupportsVariant(NSDictionary *entry, NSString *variant) { return OrTTSValidOwnCatalogEntry(entry)&&[entry[@"supported_variants"]containsObject:variant]; }

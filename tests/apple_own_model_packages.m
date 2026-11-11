#import "OwnModelPackage.h"

int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc!=4) return 2; // PTQ, standard Q8, legacy manifests; no weights.
        NSData *ptq=[NSData dataWithContentsOfFile:@(argv[1])];
        NSData *q8=[NSData dataWithContentsOfFile:@(argv[2])];
        NSData *legacy=[NSData dataWithContentsOfFile:@(argv[3])];
        NSCAssert(OrTTSVerifiedOwnManifest(ptq,OrTTSOwnPackagePTQ),@"published PTQ pin");
        NSCAssert(OrTTSVerifiedOwnManifest(q8,OrTTSOwnPackageQ8),@"standard pin retained");
        NSCAssert(OrTTSVerifiedOwnManifest(legacy,OrTTSOwnPackageLegacy),@"legacy pin retained");
        NSCAssert(!OrTTSVerifiedOwnManifest(q8,OrTTSOwnPackagePTQ),@"root Q8 manifest must not substitute PTQ");
        NSCAssert(!OrTTSVerifiedOwnManifest(ptq,OrTTSOwnPackageQ8),@"PTQ must not overwrite standard package");
        NSMutableData *tampered=[ptq mutableCopy]; [tampered appendData:[@" " dataUsingEncoding:NSUTF8StringEncoding]];
        NSCAssert(!OrTTSVerifiedOwnManifest(tampered,OrTTSOwnPackagePTQ),@"byte identity required");
        NSCAssert(!OrTTSVerifiedOwnManifest(nil,OrTTSOwnPackagePTQ),@"missing manifest");
        NSCAssert(!OrTTSOwnPackageInfo(99),@"unknown package");
        NSDictionary *info=OrTTSOwnPackageInfo(OrTTSOwnPackagePTQ);
        NSCAssert([info[@"p3_only"] boolValue],@"P3 only");
        NSCAssert(OrTTSOwnPackageSupportsVariant(OrTTSOwnPackagePTQ,@"P3"),@"PTQ P3");
        NSCAssert(!OrTTSOwnPackageSupportsVariant(OrTTSOwnPackagePTQ,@"P5"),@"reject PTQ P5");
        NSCAssert(OrTTSOwnPackageSupportsVariant(OrTTSOwnPackageQ8,@"P5"),@"retain standard P5");
        NSCAssert([info[@"directory"] isEqual:@"models-ptq-q4"],@"separate installation");
        NSCAssert([info[@"manifest_url"] containsString:@"/variants/ptq-q4/"],@"nested artifact path");
        puts("PASS: pinned manifests, wrong-package/tamper rejection, PTQ directory and P3 scope");
    }
    return 0;
}

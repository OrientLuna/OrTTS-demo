#import <Foundation/Foundation.h>

typedef NS_ENUM(NSInteger, OrTTSOwnPackageKind) {
    OrTTSOwnPackageQ8 = 0,
    OrTTSOwnPackageLegacy = 1,
    OrTTSOwnPackagePTQ = 2,
};

NSDictionary *OrTTSOwnPackageInfo(NSInteger kind);
NSDictionary *OrTTSVerifiedOwnManifest(NSData *data, NSInteger kind);
BOOL OrTTSOwnPackageSupportsVariant(NSInteger kind, NSString *variant);

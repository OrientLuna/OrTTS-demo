#import <Foundation/Foundation.h>
NSArray<NSString *> *OrTTSOwnRepositories(NSDictionary *response);
NSArray<NSDictionary *> *OrTTSOwnManifestSources(NSString *repo, NSDictionary *response);
NSDictionary *OrTTSNormalizeOwnModel(NSDictionary *source, NSData *data);
BOOL OrTTSValidOwnCatalogEntry(NSDictionary *entry);
NSArray<NSDictionary *> *OrTTSMergeOwnCatalogs(NSArray<NSArray *> *catalogs);
NSArray<NSDictionary *> *OrTTSRefreshOwnCatalog(NSArray<NSDictionary *> *previous, NSError **error);
NSArray<NSDictionary *> *OrTTSLoadOwnCatalog(NSURL *file);
BOOL OrTTSSaveOwnCatalog(NSURL *file, NSArray<NSDictionary *> *models, NSError **error);

NSString *OrTTSOwnModelTitle(NSDictionary *entry);

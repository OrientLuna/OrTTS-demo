#import "WorkQueue.h"
dispatch_queue_t OrTTSDemoQueue(void) {
    static dispatch_queue_t queue; static dispatch_once_t once;
    dispatch_once(&once, ^{ queue=dispatch_queue_create("com.orient.ortts.demo.worker",DISPATCH_QUEUE_SERIAL); });
    return queue;
}

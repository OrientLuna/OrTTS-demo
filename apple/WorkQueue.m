#import "WorkQueue.h"
void OrTTSPerformWithStack(dispatch_block_t block) {
    dispatch_semaphore_t done=dispatch_semaphore_create(0);
    NSThread *thread=[[NSThread alloc]initWithBlock:^{
        @autoreleasepool { @try { block(); } @finally { dispatch_semaphore_signal(done); } }
    }];
    thread.name=@"OrTTS synthesis";
    thread.stackSize=8*1024*1024;
    [thread start];
    dispatch_semaphore_wait(done,DISPATCH_TIME_FOREVER);
}
dispatch_queue_t OrTTSDemoQueue(void) {
    static dispatch_queue_t queue; static dispatch_once_t once;
    dispatch_once(&once, ^{ queue=dispatch_queue_create("com.orient.ortts.demo.worker",DISPATCH_QUEUE_SERIAL); });
    return queue;
}

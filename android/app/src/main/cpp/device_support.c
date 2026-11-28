#include <jni.h>
#include <sys/auxv.h>
#include <asm/hwcap.h>
/* Compile this small check for baseline ARM64, before loading optimized code. */
JNIEXPORT jboolean JNICALL Java_com_orient_ortts_demo_DeviceSupport_supportsCurrentRuntime(JNIEnv *env,jclass type) {
 (void)env;(void)type;
 const unsigned long required=HWCAP_ASIMD|HWCAP_FPHP|HWCAP_ASIMDHP|HWCAP_ASIMDDP;
 if((getauxval(AT_HWCAP)&required)!=required)return JNI_FALSE;
#ifndef ORTTS_DEVICE_DOTPROD_ONLY
 if(!(getauxval(AT_HWCAP2)&HWCAP2_I8MM))return JNI_FALSE;
#endif
 return JNI_TRUE;
}

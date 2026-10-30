#include <jni.h>
#include <sys/auxv.h>
#include <asm/hwcap.h>
/* Compile this small check for baseline ARM64, before loading optimized code. */
JNIEXPORT jboolean JNICALL Java_com_orient_ortts_demo_DeviceSupport_supportsCurrentRuntime(JNIEnv *env,jclass type) {
 (void)env;(void)type;
 unsigned long required=HWCAP_ASIMD|HWCAP_FPHP|HWCAP_ASIMDHP|HWCAP_ASIMDDP;
 return ((getauxval(AT_HWCAP)&required)==required && (getauxval(AT_HWCAP2)&HWCAP2_I8MM))?JNI_TRUE:JNI_FALSE;
}

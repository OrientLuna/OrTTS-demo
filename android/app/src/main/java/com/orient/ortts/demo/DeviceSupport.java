package com.orient.ortts.demo;
final class DeviceSupport {
 static { System.loadLibrary("ortts_device"); }
 static native boolean supportsCurrentRuntime();
}

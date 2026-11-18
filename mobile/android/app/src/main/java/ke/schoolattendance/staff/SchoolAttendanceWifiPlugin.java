package ke.schoolattendance.staff;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.net.wifi.WifiInfo;
import android.net.wifi.WifiManager;
import android.os.Build;

import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "SchoolAttendanceWifi")
public class SchoolAttendanceWifiPlugin extends Plugin {
    @PluginMethod
    public void getInfo(com.getcapacitor.PluginCall call) {
        if (ContextCompat.checkSelfPermission(getContext(), Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            JSObject result = new JSObject();
            result.put("ssid", null);
            result.put("bssid", null);
            result.put("available", false);
            result.put("reason", "Location permission is required for Wi-Fi BSSID access.");
            call.resolve(result);
            return;
        }
        WifiManager manager = (WifiManager) getContext().getApplicationContext()
                .getSystemService(Context.WIFI_SERVICE);
        if (manager == null) {
            call.resolve(wifiUnavailable("Wi-Fi service is unavailable."));
            return;
        }
        WifiInfo info = manager.getConnectionInfo();
        String bssid = info == null ? null : info.getBSSID();
        JSObject result = new JSObject();
        result.put("ssid", info == null ? null : info.getSSID());
        result.put("bssid", bssid);
        result.put("available", bssid != null);
        if (bssid == null) result.put("reason", "Wi-Fi BSSID is unavailable.");
        call.resolve(result);
    }

    private JSObject wifiUnavailable(String reason) {
        JSObject result = new JSObject();
        result.put("ssid", null);
        result.put("bssid", null);
        result.put("available", false);
        result.put("reason", reason);
        return result;
    }
}

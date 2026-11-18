package ke.schoolattendance.staff;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationManager;

import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "SchoolAttendanceLocation")
public class SchoolAttendanceLocationPlugin extends Plugin {
    @PluginMethod
    public void requestPermissions(com.getcapacitor.PluginCall call) {
        requestPermissions(call);
    }
    @PluginMethod
    public void getCurrentLocation(com.getcapacitor.PluginCall call) {
        if (ContextCompat.checkSelfPermission(getContext(), Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED &&
            ContextCompat.checkSelfPermission(getContext(), Manifest.permission.ACCESS_COARSE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            JSObject denied = new JSObject();
            denied.put("available", false);
            denied.put("reason", "Location permission is required.");
            call.resolve(denied);
            return;
        }
        LocationManager manager = (LocationManager) getContext().getSystemService(Context.LOCATION_SERVICE);
        Location best = null;
        if (manager != null) {
            for (String provider : manager.getProviders(true)) {
                try {
                    Location candidate = manager.getLastKnownLocation(provider);
                    if (candidate != null && (best == null || candidate.getTime() > best.getTime())) {
                        best = candidate;
                    }
                } catch (SecurityException ignored) {
                }
            }
        }
        if (best == null) {
            JSObject unavailable = new JSObject();
            unavailable.put("available", false);
            unavailable.put("reason", "Location is temporarily unavailable.");
            call.resolve(unavailable);
            return;
        }
        JSObject location = new JSObject();
        location.put("latitude", best.getLatitude());
        location.put("longitude", best.getLongitude());
        location.put("accuracyMeters", best.hasAccuracy() ? best.getAccuracy() : 9999);
        location.put("timestamp", java.time.Instant.ofEpochMilli(best.getTime()).toString());
        JSObject result = new JSObject();
        result.put("available", true);
        result.put("location", location);
        call.resolve(result);
    }
}

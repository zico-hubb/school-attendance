package ke.schoolattendance.staff;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(android.os.Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        registerPlugin(SchoolAttendanceDeviceIdentityPlugin.class);
        registerPlugin(SchoolAttendanceLocationPlugin.class);
        registerPlugin(SchoolAttendanceWifiPlugin.class);
    }
}

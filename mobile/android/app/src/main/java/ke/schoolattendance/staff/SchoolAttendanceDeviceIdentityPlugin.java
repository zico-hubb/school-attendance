package ke.schoolattendance.staff;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.security.PublicKey;
import java.security.PrivateKey;
import java.util.Base64;

@CapacitorPlugin(name = "SchoolAttendanceDeviceIdentity")
public class SchoolAttendanceDeviceIdentityPlugin extends Plugin {
    private static final String ALIAS = "school_attendance_device_p256";

    private KeyPair loadOrCreateKeyPair() throws Exception {
        KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
        keyStore.load(null);
        if (keyStore.containsAlias(ALIAS)) {
            PublicKey publicKey = keyStore.getCertificate(ALIAS).getPublicKey();
            PrivateKey privateKey = ((KeyStore.PrivateKeyEntry)
                    keyStore.getEntry(ALIAS, null)).getPrivateKey();
            return new KeyPair(publicKey, privateKey);
        }
        KeyPairGenerator generator = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore");
        generator.initialize(new KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setUserAuthenticationRequired(false)
                .setKeySize(256)
                .build());
        return generator.generateKeyPair();
    }

    @PluginMethod
    public void registerPublicKey(com.getcapacitor.PluginCall call) {
        try {
            KeyPair pair = loadOrCreateKeyPair();
            if (!(pair.getPublic() instanceof ECPublicKey)) {
                call.reject("Generated key is not P-256.");
                return;
            }
            java.security.spec.X509EncodedKeySpec spec =
                    new java.security.spec.X509EncodedKeySpec(pair.getPublic().getEncoded());
            String pem = "-----BEGIN PUBLIC KEY-----\n"
                    + Base64.getMimeEncoder(64, new byte[]{'\n'}).encodeToString(spec.getEncoded())
                    + "\n-----END PUBLIC KEY-----";
            JSObject result = new JSObject();
            result.put("available", true);
            JSObject value = new JSObject();
            value.put("keyId", ALIAS);
            value.put("publicKey", pem);
            value.put("algorithm", "ECDSA_P256_SHA256");
            result.put("value", value);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("Android key generation failed: " + error.getClass().getSimpleName());
        }
    }

    @PluginMethod
    public void signChallenge(com.getcapacitor.PluginCall call) {
        String challenge = call.getString("challenge");
        if (challenge == null) {
            call.reject("Challenge is required.");
            return;
        }
        try {
            KeyPair pair = loadOrCreateKeyPair();
            Signature signature = Signature.getInstance("SHA256withECDSA");
            signature.initSign(pair.getPrivate());
            signature.update(challenge.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            JSObject result = new JSObject();
            result.put("available", true);
            JSObject value = new JSObject();
            value.put("signature", Base64.getEncoder().encodeToString(signature.sign()));
            result.put("value", value);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("Challenge signing failed: " + error.getClass().getSimpleName());
        }
    }
}

package com.regtrack.backend.security;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

class WebhookCryptoTest {

    @Test
    void hmacMatchesRfc4231TestVector() {
        byte[] data = "what do ya want for nothing?".getBytes(StandardCharsets.UTF_8);
        String hex = WebhookHmacFilter.hmacSha256Hex(data, "Jefe");

        assertThat(hex).isEqualTo("5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
    }

    @Test
    void sha256MatchesKnownVector() {
        assertThat(WebhookHmacFilter.sha256Hex("abc"))
                .isEqualTo("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }

    @Test
    void hmacIsDeterministicAndKeySensitive() {
        byte[] body = "{\"url\":\"https://www.rbi.org.in/x\"}".getBytes(StandardCharsets.UTF_8);

        String sig1 = WebhookHmacFilter.hmacSha256Hex(body, "secret-a");
        String sig2 = WebhookHmacFilter.hmacSha256Hex(body, "secret-a");
        String sig3 = WebhookHmacFilter.hmacSha256Hex(body, "secret-b");

        assertThat(sig1).isEqualTo(sig2);
        assertThat(sig1).isNotEqualTo(sig3);
        assertThat(sig1).hasSize(64);
    }
}

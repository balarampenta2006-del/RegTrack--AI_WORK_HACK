package com.regtrack.backend.security;

import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class CachedBodyHttpServletRequest extends HttpServletRequestWrapper {

    private final byte[] cachedBody;

    public CachedBodyHttpServletRequest(HttpServletRequest request, byte[] cachedBody) {
        super(request);
        this.cachedBody = cachedBody;
    }

    public byte[] getCachedBody() {
        return cachedBody;
    }

    @Override
    public ServletInputStream getInputStream() {
        ByteArrayInputStream in = new ByteArrayInputStream(cachedBody);
        return new ServletInputStream() {
            @Override
            public boolean isFinished() {
                return in.available() == 0;
            }

            @Override
            public boolean isReady() {
                return true;
            }

            @Override
            public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException();
            }

            @Override
            public int read() {
                return in.read();
            }
        };
    }

    @Override
    public BufferedReader getReader() {
        String encoding = getCharacterEncoding() != null ? getCharacterEncoding() : StandardCharsets.UTF_8.name();
        return new BufferedReader(new InputStreamReader(new ByteArrayInputStream(cachedBody),
                java.nio.charset.Charset.forName(encoding)));
    }
}

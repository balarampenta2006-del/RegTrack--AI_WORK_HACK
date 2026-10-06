package com.regtrack.backend.config;

import com.regtrack.backend.security.JwtAuthenticationFilter;
import com.regtrack.backend.security.WebhookHmacFilter;
import com.regtrack.backend.security.UserPrincipal;
import tools.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

import java.util.Map;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final WebhookHmacFilter webhookHmacFilter;
    private final ObjectMapper objectMapper;

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(AbstractHttpConfigurer::disable)
                .cors(cors -> {})
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .requestMatchers("/api/auth/**").permitAll()
                        .requestMatchers("/api/webhooks/**").permitAll()
                        .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                        .requestMatchers("/actuator/**").hasRole("ADMIN")
                        .requestMatchers(HttpMethod.POST, "/api/sources/**", "/api/companies").hasRole("ADMIN")
                        .requestMatchers(HttpMethod.PUT, "/api/sources/**", "/api/companies/*").hasRole("ADMIN")
                        .requestMatchers(HttpMethod.PUT, "/api/companies/*/profile").authenticated()
                        .requestMatchers(HttpMethod.DELETE, "/**").hasRole("ADMIN")
                        .requestMatchers("/api/audit/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(this::writeUnauthorized)
                        .accessDeniedHandler(this::writeForbidden))
                .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
                .addFilterBefore(webhookHmacFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    private void writeUnauthorized(jakarta.servlet.http.HttpServletRequest request,
                                   HttpServletResponse response,
                                   org.springframework.security.core.AuthenticationException ex)
            throws java.io.IOException {
        if (response.isCommitted()) {
            return;
        }
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getWriter(),
                Map.of("error", "unauthorized", "message", "Missing or invalid authentication token"));
    }

    private void writeForbidden(jakarta.servlet.http.HttpServletRequest request,
                                HttpServletResponse response,
                                org.springframework.security.access.AccessDeniedException ex)
            throws java.io.IOException {
        if (response.isCommitted()) {
            return;
        }
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getWriter(),
                Map.of("error", "forbidden", "message", "You do not have permission to access this resource"));
    }
}

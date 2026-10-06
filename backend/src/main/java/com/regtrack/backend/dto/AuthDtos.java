package com.regtrack.backend.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public final class AuthDtos {

    private AuthDtos() {
    }

    public record RegisterRequest(
            @NotBlank @Email String email,
            @NotBlank @Size(min = 8, max = 100) String password,
            @NotBlank @Size(max = 190) String fullName,
            @Size(max = 190) String companyName,
            @Size(max = 120) String industry) {
    }

    public record LoginRequest(
            @NotBlank @Email String email,
            @NotBlank String password) {
    }

    public record UserResponse(
            Long id,
            String email,
            String fullName,
            String role,
            Long companyId,
            String companyName) {
    }

    public record AuthResponse(
            String token,
            String type,
            long expiresInSeconds,
            UserResponse user) {
    }
}

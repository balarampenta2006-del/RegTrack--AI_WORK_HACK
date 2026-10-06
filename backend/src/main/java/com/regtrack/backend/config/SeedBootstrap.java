package com.regtrack.backend.config;

import com.regtrack.backend.model.RegulationSource;
import com.regtrack.backend.model.Role;
import com.regtrack.backend.model.User;
import com.regtrack.backend.repository.RegulationSourceRepository;
import com.regtrack.backend.repository.UserRepository;
import com.regtrack.backend.service.AuditService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Component
@RequiredArgsConstructor
@Slf4j
public class SeedBootstrap implements ApplicationRunner {

    private final UserRepository userRepository;
    private final RegulationSourceRepository sourceRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuditService auditService;

    @Value("${regtrack.seed.enabled}")
    private boolean seedEnabled;

    @Value("${regtrack.seed.admin-email}")
    private String adminEmail;

    @Value("${regtrack.seed.admin-password}")
    private String adminPassword;

    @Value("${regtrack.seed.admin-name}")
    private String adminName;

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (!seedEnabled) {
            return;
        }
        seedAdmin();
        seedSources();
    }

    private void seedAdmin() {
        if (userRepository.countByRole(Role.ADMIN) > 0 || userRepository.existsByEmail(adminEmail)) {
            return;
        }
        User admin = User.builder()
                .email(adminEmail)
                .passwordHash(passwordEncoder.encode(adminPassword))
                .fullName(adminName)
                .role(Role.ADMIN)
                .enabled(true)
                .build();
        userRepository.save(admin);
        auditService.record("system", "SYSTEM", "SEED_ADMIN", "User", admin.getId(),
                "Seeded initial admin account: " + adminEmail, null);
        log.info("Seeded admin account {}", adminEmail);
    }

    private void seedSources() {
        if (sourceRepository.count() > 0) {
            return;
        }
        List<RegulationSource> defaults = List.of(
                RegulationSource.builder()
                        .code("MCA")
                        .name("Ministry of Corporate Affairs")
                        .agency("MCA")
                        .baseUrl("https://www.mca.gov.in")
                        .watchUrl("https://www.mca.gov.in/content/mca/global/en/acts-rules.html")
                        .active(true)
                        .build(),
                RegulationSource.builder()
                        .code("RBI")
                        .name("Reserve Bank of India")
                        .agency("RBI")
                        .baseUrl("https://www.rbi.org.in")
                        .watchUrl("https://www.rbi.org.in/Scripts/BS_ViewMasNotifications.aspx")
                        .active(true)
                        .build(),
                RegulationSource.builder()
                        .code("SEBI")
                        .name("Securities and Exchange Board of India")
                        .agency("SEBI")
                        .baseUrl("https://www.sebi.gov.in")
                        .watchUrl("https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=2&ssid=9&smid=11")
                        .active(true)
                        .build());
        sourceRepository.saveAll(defaults);
        auditService.record("system", "SYSTEM", "SEED_SOURCES", "RegulationSource", null,
                "Seeded default sources: MCA, RBI, SEBI", null);
        log.info("Seeded default regulation sources (MCA, RBI, SEBI)");
    }
}

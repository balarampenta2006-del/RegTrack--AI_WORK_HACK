package com.regtrack.backend.repository;

import com.regtrack.backend.model.CompanyProfile;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface CompanyProfileRepository extends JpaRepository<CompanyProfile, Long> {

    Optional<CompanyProfile> findByCompanyId(Long companyId);
}

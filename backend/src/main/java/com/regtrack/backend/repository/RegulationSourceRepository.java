package com.regtrack.backend.repository;

import com.regtrack.backend.model.RegulationSource;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface RegulationSourceRepository extends JpaRepository<RegulationSource, Long> {

    Optional<RegulationSource> findByCode(String code);

    List<RegulationSource> findByActiveTrue();
}

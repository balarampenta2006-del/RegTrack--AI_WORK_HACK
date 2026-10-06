package com.regtrack.backend.repository;

import com.regtrack.backend.model.RegulationVersion;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface RegulationVersionRepository extends JpaRepository<RegulationVersion, Long> {

    List<RegulationVersion> findByRegulationIdOrderByVersionNoDesc(Long regulationId);

    Optional<RegulationVersion> findFirstByRegulationIdAndCurrentTrue(Long regulationId);

    Optional<RegulationVersion> findByRegulationIdAndVersionNo(Long regulationId, Integer versionNo);

    long countByRegulationId(Long regulationId);

    @Modifying
    @Query("update RegulationVersion v set v.current = false where v.regulationId = :regulationId")
    void clearCurrentFlags(@Param("regulationId") Long regulationId);
}

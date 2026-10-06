package com.regtrack.backend.repository;

import com.regtrack.backend.model.Regulation;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface RegulationRepository extends JpaRepository<Regulation, Long> {

    Optional<Regulation> findByUrl(String url);

    List<Regulation> findBySourceIdOrderByCreatedAtDesc(Long sourceId);
}

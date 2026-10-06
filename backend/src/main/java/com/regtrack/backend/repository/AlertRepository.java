package com.regtrack.backend.repository;

import com.regtrack.backend.model.Alert;
import com.regtrack.backend.model.AlertStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface AlertRepository extends JpaRepository<Alert, Long> {

    List<Alert> findByCompanyIdOrderByCreatedAtDesc(Long companyId);

    List<Alert> findAllByOrderByCreatedAtDesc();

    List<Alert> findByCompanyIdAndStatusOrderByCreatedAtDesc(Long companyId, AlertStatus status);

    List<Alert> findByStatusOrderByCreatedAtDesc(AlertStatus status);

    long countByStatus(AlertStatus status);
}

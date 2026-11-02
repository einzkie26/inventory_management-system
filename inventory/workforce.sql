CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    assigned_to INT NOT NULL,
    created_by INT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'assigned',
    notes TEXT NOT NULL,
    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    picked_up_at DATETIME NULL,
    delivered_at DATETIME NULL,
    cancelled_at DATETIME NULL,
    CONSTRAINT uq_delivery_order UNIQUE (order_id),
    CONSTRAINT chk_delivery_status CHECK (status IN ('assigned','in_transit','delivered','cancelled')),
    CONSTRAINT fk_deliveries_order FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE RESTRICT,
    CONSTRAINT fk_deliveries_assignee FOREIGN KEY (assigned_to) REFERENCES users(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_deliveries_creator FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    INDEX ix_delivery_assignee_status (assigned_to,status),
    INDEX ix_delivery_status_date (status,assigned_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS delivery_events (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    delivery_id INT NOT NULL,
    status VARCHAR(16) NOT NULL,
    actor_id INT NOT NULL,
    notes VARCHAR(255) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_delivery_events_delivery FOREIGN KEY (delivery_id) REFERENCES deliveries(delivery_id) ON DELETE RESTRICT,
    CONSTRAINT fk_delivery_events_actor FOREIGN KEY (actor_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    INDEX ix_delivery_events_delivery (delivery_id,event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS stock_checks (
    check_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    expected_quantity INT NOT NULL,
    counted_quantity INT NOT NULL,
    difference INT NOT NULL,
    product_version INT NOT NULL,
    status VARCHAR(16) NOT NULL,
    checked_by INT NOT NULL,
    checked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    corrected_by INT NULL,
    corrected_at DATETIME NULL,
    notes TEXT NOT NULL,
    CONSTRAINT chk_stock_check_count CHECK (expected_quantity>=0 AND counted_quantity>=0),
    CONSTRAINT chk_stock_check_status CHECK (status IN ('matched','flagged','corrected','superseded')),
    CONSTRAINT fk_stock_check_product FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE RESTRICT,
    CONSTRAINT fk_stock_check_employee FOREIGN KEY (checked_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_stock_check_admin FOREIGN KEY (corrected_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    INDEX ix_stock_check_status (status,checked_at),
    INDEX ix_stock_check_product (product_id,check_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

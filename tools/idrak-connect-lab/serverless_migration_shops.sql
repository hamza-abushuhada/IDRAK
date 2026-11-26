-- Multi-shop upgrade for the isolated Lab PostgreSQL database (Lab-only; never
-- touches the IDRAK application database). Idempotent, one transaction.
-- Every existing row is assigned to the legacy shop 'idrak-test-shop-001', so row
-- ids, event cursors, invoice numbers and event ids are unchanged.
CREATE TABLE IF NOT EXISTS idrak_lab_source.shops (
  shop_id text PRIMARY KEY CHECK (shop_id ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
  name text NOT NULL, token_hash text UNIQUE,
  disabled integer NOT NULL DEFAULT 0, created_at text NOT NULL
);
INSERT INTO idrak_lab_source.shops(shop_id, name, created_at)
VALUES ('idrak-test-shop-001', 'متجر التجربة', to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'))
ON CONFLICT (shop_id) DO NOTHING;

-- products: PK (sku) -> (shop_id, sku)
ALTER TABLE idrak_lab_source.products ADD COLUMN IF NOT EXISTS shop_id text NOT NULL DEFAULT 'idrak-test-shop-001' REFERENCES idrak_lab_source.shops(shop_id);
ALTER TABLE idrak_lab_source.products ALTER COLUMN shop_id DROP DEFAULT;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                 WHERE i.indrelid = 'idrak_lab_source.products'::regclass AND i.indisprimary AND a.attname = 'shop_id') THEN
    ALTER TABLE idrak_lab_source.products DROP CONSTRAINT products_pkey;
    ALTER TABLE idrak_lab_source.products ADD PRIMARY KEY (shop_id, sku);
  END IF;
END $$;

-- orders: per-shop invoice sequence and per-shop external ids
ALTER TABLE idrak_lab_source.orders ADD COLUMN IF NOT EXISTS shop_id text NOT NULL DEFAULT 'idrak-test-shop-001' REFERENCES idrak_lab_source.shops(shop_id);
ALTER TABLE idrak_lab_source.orders ALTER COLUMN shop_id DROP DEFAULT;
ALTER TABLE idrak_lab_source.orders ADD COLUMN IF NOT EXISTS order_no bigint;
UPDATE idrak_lab_source.orders SET order_no = id WHERE order_no IS NULL;
UPDATE idrak_lab_source.orders SET external_id = CASE channel WHEN 'pos' THEN 'POS-' ELSE 'WEB-' END || lpad(id::text, 6, '0') WHERE external_id IS NULL;
ALTER TABLE idrak_lab_source.orders ALTER COLUMN order_no SET NOT NULL;
ALTER TABLE idrak_lab_source.orders ALTER COLUMN external_id SET NOT NULL;
ALTER TABLE idrak_lab_source.orders DROP CONSTRAINT IF EXISTS orders_external_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS orders_shop_external_key ON idrak_lab_source.orders(shop_id, external_id);
CREATE UNIQUE INDEX IF NOT EXISTS orders_shop_order_no_key ON idrak_lab_source.orders(shop_id, order_no);
CREATE UNIQUE INDEX IF NOT EXISTS orders_id_shop_key ON idrak_lab_source.orders(id, shop_id);
CREATE INDEX IF NOT EXISTS orders_shop_channel_idx ON idrak_lab_source.orders(shop_id, channel, id);

-- order_items: shop_id must match the parent order's shop (composite FK)
ALTER TABLE idrak_lab_source.order_items ADD COLUMN IF NOT EXISTS shop_id text NOT NULL DEFAULT 'idrak-test-shop-001';
ALTER TABLE idrak_lab_source.order_items ALTER COLUMN shop_id DROP DEFAULT;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'order_items_order_shop_fk') THEN
    ALTER TABLE idrak_lab_source.order_items ADD CONSTRAINT order_items_order_shop_fk
      FOREIGN KEY (order_id, shop_id) REFERENCES idrak_lab_source.orders(id, shop_id);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS order_items_order_idx ON idrak_lab_source.order_items(order_id);

-- source_events: event_id unique per shop; cursor index per shop
ALTER TABLE idrak_lab_source.source_events ADD COLUMN IF NOT EXISTS shop_id text NOT NULL DEFAULT 'idrak-test-shop-001' REFERENCES idrak_lab_source.shops(shop_id);
ALTER TABLE idrak_lab_source.source_events ALTER COLUMN shop_id DROP DEFAULT;
ALTER TABLE idrak_lab_source.source_events DROP CONSTRAINT IF EXISTS source_events_event_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS source_events_shop_event_key ON idrak_lab_source.source_events(shop_id, event_id);
CREATE INDEX IF NOT EXISTS source_events_cursor_idx ON idrak_lab_source.source_events(shop_id, channel, seq);

-- receiver
ALTER TABLE idrak_lab_receiver.received_events ADD COLUMN IF NOT EXISTS shop_id text NOT NULL DEFAULT 'idrak-test-shop-001';
ALTER TABLE idrak_lab_receiver.received_events ALTER COLUMN shop_id DROP DEFAULT;
ALTER TABLE idrak_lab_receiver.received_events DROP CONSTRAINT IF EXISTS received_events_event_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS received_events_shop_event_key ON idrak_lab_receiver.received_events(shop_id, event_id);

ALTER TABLE idrak_lab_receiver.synced_orders ADD COLUMN IF NOT EXISTS shop_id text NOT NULL DEFAULT 'idrak-test-shop-001';
ALTER TABLE idrak_lab_receiver.synced_orders ALTER COLUMN shop_id DROP DEFAULT;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                 WHERE i.indrelid = 'idrak_lab_receiver.synced_orders'::regclass AND i.indisprimary AND a.attname = 'shop_id') THEN
    ALTER TABLE idrak_lab_receiver.synced_orders DROP CONSTRAINT synced_orders_pkey;
    ALTER TABLE idrak_lab_receiver.synced_orders ADD PRIMARY KEY (shop_id, source_id, external_id);
  END IF;
END $$;

ALTER TABLE idrak_lab_receiver.synced_inventory ADD COLUMN IF NOT EXISTS shop_id text NOT NULL DEFAULT 'idrak-test-shop-001';
ALTER TABLE idrak_lab_receiver.synced_inventory ALTER COLUMN shop_id DROP DEFAULT;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                 WHERE i.indrelid = 'idrak_lab_receiver.synced_inventory'::regclass AND i.indisprimary AND a.attname = 'shop_id') THEN
    ALTER TABLE idrak_lab_receiver.synced_inventory DROP CONSTRAINT synced_inventory_pkey;
    ALTER TABLE idrak_lab_receiver.synced_inventory ADD PRIMARY KEY (shop_id, source_id, sku);
  END IF;
END $$;

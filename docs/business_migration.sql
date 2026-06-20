-- ============================================================
-- 经营主项归档 SQL 迁移脚本
-- 生成时间: 2026-06-20 16:21:04
-- 目标数据库: qhi_enterprise.db
-- ============================================================

-- ==== papers 表扩展字段 ====
ALTER TABLE papers ADD COLUMN unit TEXT;
ALTER TABLE papers ADD COLUMN pricing_tier INTEGER DEFAULT 1;
ALTER TABLE papers ADD COLUMN sale_price REAL DEFAULT 0;
ALTER TABLE papers ADD COLUMN default_outsource INTEGER DEFAULT 0;
ALTER TABLE papers ADD COLUMN can_rename INTEGER DEFAULT 0;
ALTER TABLE papers ADD COLUMN min_charge REAL DEFAULT 0;
ALTER TABLE papers ADD COLUMN alert_price REAL DEFAULT 0;
ALTER TABLE papers ADD COLUMN floor_price REAL DEFAULT 0;
ALTER TABLE papers ADD COLUMN production_score INTEGER DEFAULT 0;
ALTER TABLE papers ADD COLUMN production_role TEXT;
ALTER TABLE papers ADD COLUMN stat_tag TEXT;
ALTER TABLE papers ADD COLUMN stat_coefficient REAL DEFAULT 1.0;
ALTER TABLE papers ADD COLUMN detail_print INTEGER DEFAULT 1;
ALTER TABLE papers ADD COLUMN consume_score INTEGER DEFAULT 0;
ALTER TABLE papers ADD COLUMN cost_price REAL DEFAULT 0;
ALTER TABLE papers ADD COLUMN parent_code TEXT;
ALTER TABLE papers ADD COLUMN server_business_id TEXT;
ALTER TABLE papers ADD COLUMN server_spec_id TEXT;
ALTER TABLE papers ADD COLUMN is_master INTEGER DEFAULT 1;

-- ==== processes 表扩展字段 ====
ALTER TABLE processes ADD COLUMN unit TEXT;
ALTER TABLE processes ADD COLUMN pricing_tier INTEGER DEFAULT 1;
ALTER TABLE processes ADD COLUMN sale_price REAL DEFAULT 0;
ALTER TABLE processes ADD COLUMN default_outsource INTEGER DEFAULT 0;
ALTER TABLE processes ADD COLUMN can_rename INTEGER DEFAULT 0;
ALTER TABLE processes ADD COLUMN min_charge REAL DEFAULT 0;
ALTER TABLE processes ADD COLUMN alert_price REAL DEFAULT 0;
ALTER TABLE processes ADD COLUMN floor_price REAL DEFAULT 0;
ALTER TABLE processes ADD COLUMN production_score INTEGER DEFAULT 0;
ALTER TABLE processes ADD COLUMN production_role TEXT;
ALTER TABLE processes ADD COLUMN stat_tag TEXT;
ALTER TABLE processes ADD COLUMN stat_coefficient REAL DEFAULT 1.0;
ALTER TABLE processes ADD COLUMN detail_print INTEGER DEFAULT 1;
ALTER TABLE processes ADD COLUMN consume_score INTEGER DEFAULT 0;
ALTER TABLE processes ADD COLUMN cost_price REAL DEFAULT 0;
ALTER TABLE processes ADD COLUMN parent_code TEXT;
ALTER TABLE processes ADD COLUMN server_business_id TEXT;
ALTER TABLE processes ADD COLUMN server_spec_id TEXT;
ALTER TABLE processes ADD COLUMN is_master INTEGER DEFAULT 1;

-- ==== papers 主项（经营主项 → 纸张库）====
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('10', '彩色机打印A3+双面', '彩色输出类', '0221295c-d868-4b0a-914c-02bc7f1f9ee9', 1, 1, '2026-06-20 16:20:21');
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('11', '彩色机打印A3+单面', '彩色输出类', '1226cf46-74e3-4be6-b616-2766b6262ce7', 1, 1, '2026-06-20 16:20:21');
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('12', '科美彩色打印', '彩色输出类', 'fe7f3d77-1e13-45d4-a0e4-e45c980d0d6e', 1, 1, '2026-06-20 16:20:21');
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('13', '黑白机打印', '黑白输出类', 'cc5addfd-65d6-4ff9-b219-8fdf9b107477', 1, 1, '2026-06-20 16:20:21');
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('14', 'HP12000', '大幅面类', '3752386d-2e7d-490b-aecf-307cbbdeeee4', 1, 1, '2026-06-20 16:20:21');
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('16', '写真+喷绘', '大幅面类', 'f52c3975-a6f8-4c40-b690-fe29526d1d6b', 1, 1, '2026-06-20 16:20:21');
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('17', '数码打样-爱普生', '打样类', 'eb83fc4a-ecf7-42fb-a098-a152c8add5df', 1, 1, '2026-06-20 16:20:21');
INSERT INTO papers (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('18', '大机器艺术纸', '特种纸类', '4dfcf688-e7bc-4183-9bb2-dcd41bc8e242', 1, 1, '2026-06-20 16:20:21');

-- ==== papers 子项 ====
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('10-001', 'A3+双面铜版纸200g', '张', 1, 3.5, 0, 0, 10.0, 1.0, 0.8, 5, '彩色打印机长', '彩色/A3+/双面/铜版200g', 1.0, 1, 10, 2.0, '惠普/科美/爱普生/黑白设备通用', '10', '819fec12-1ac9-4a25-ac6b-367205159ce2', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('10-002', 'A3+双面铜版纸250g', '张', 1, 4.0, 0, 0, 10.0, 1.2, 0.9, 5, '彩色打印机长', '彩色/A3+/双面/铜版250g', 1.0, 1, 10, 2.3, '', '10', NULL, 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('10-003', 'A3+双面哑粉纸200g', '张', 1, 3.8, 0, 0, 10.0, 1.1, 0.85, 5, '彩色打印机长', '彩色/A3+/双面/哑粉200g', 1.0, 1, 10, 2.1, '', '10', NULL, 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('11-001', 'A3+单面铜版纸200g', '张', 1, 2.5, 0, 0, 10.0, 0.8, 0.6, 4, '彩色打印机长', '彩色/A3+/单面/铜版200g', 1.0, 1, 8, 1.5, '', '11', '05b15d21-6e27-4fc4-9464-e02c0cdd17f6', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('11-002', 'A3+单面铜版纸250g', '张', 1, 3.0, 0, 0, 10.0, 0.9, 0.7, 4, '彩色打印机长', '彩色/A3+/单面/铜版250g', 1.0, 1, 8, 1.8, '', '11', NULL, 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('12-001', '科美彩印铜版纸200g', '张', 1, 2.0, 0, 0, 10.0, 0.6, 0.5, 4, '科美打印机长', '彩色/科美/铜版200g', 1.0, 1, 8, 1.2, '', '12', '44f58c86-1412-4cb9-a009-275da80e2c9e', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('12-002', '科美彩印铜版纸250g', '张', 1, 2.5, 0, 0, 10.0, 0.7, 0.6, 4, '科美打印机长', '彩色/科美/铜版250g', 1.0, 1, 8, 1.5, '', '12', NULL, 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('13-001', '黑白打印A4普通纸', '张', 1, 0.3, 0, 0, 5.0, 0.1, 0.05, 2, '黑白打印机长', '黑白/A4/普通纸', 1.0, 1, 2, 0.1, '', '13', '47f83e62-9343-4fc9-838a-e8c783acb7da', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('13-002', '黑白打印A3普通纸', '张', 1, 0.5, 0, 0, 5.0, 0.15, 0.08, 2, '黑白打印机长', '黑白/A3/普通纸', 1.0, 1, 3, 0.18, '', '13', NULL, 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('14-001', 'HP12000大幅面普通纸', '平方米', 1, 25.0, 0, 0, 20.0, 8.0, 5.0, 8, '大幅面机长', '大幅面/HP12000/普通纸', 1.0, 1, 20, 12.0, '', '14', 'a0b5cfab-ce58-4f07-b8b7-b20afe6bfde6', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('14-002', 'HP12000大幅面相纸', '平方米', 1, 35.0, 0, 0, 20.0, 10.0, 8.0, 10, '大幅面机长', '大幅面/HP12000/相纸', 1.0, 1, 25, 18.0, '', '14', NULL, 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('16-001', '黑底喷绘布', '平方米', 1, 15.0, 1, 0, 20.0, 5.0, 3.5, 6, '喷绘机长', '喷绘/黑底布', 1.0, 1, 12, 8.0, '外协加工', '16', 'a38ecc6f-a950-4169-b629-c448ab4c5b8b', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('16-002', '普通喷绘布', '平方米', 1, 12.0, 1, 0, 20.0, 4.0, 3.0, 5, '喷绘机长', '喷绘/普通布', 1.0, 1, 10, 6.5, '外协加工', '16', 'f5c63a39-9ee5-43ce-9bf8-856bc01b0e3a', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('16-003', '写真背胶PP', '平方米', 1, 18.0, 1, 0, 20.0, 6.0, 4.5, 7, '喷绘机长', '写真/背胶PP', 1.0, 1, 15, 9.0, '外协加工', '16', '5daa13d9-7c3d-4e15-9b39-42b7bc1ec1c3', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('17-001', '爱普生数码打样A3+', '张', 1, 5.0, 0, 0, 10.0, 1.5, 1.0, 5, '打样机长', '打样/爱普生/A3+', 1.0, 1, 10, 2.5, '', '17', 'b478735b-7862-4a89-9799-b57721405959', 0, 1, '印刷服务', '2026-06-20 16:21:04');
INSERT INTO papers (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('18-001', '艺术纸A3+', '张', 1, 6.0, 0, 0, 15.0, 2.0, 1.5, 5, '艺术纸机长', '艺术纸/A3+', 1.0, 1, 12, 3.5, '', '18', 'cfc880cf-3853-446e-ba2f-53d771e37fe7', 0, 1, '印刷服务', '2026-06-20 16:21:04');

-- ==== processes 主项（经营主项 → 工艺库）====
INSERT INTO processes (code, name, category, server_business_id, is_master, is_active, created_at) VALUES ('15', '文本装订', '后道类', '1d183416-f10a-4636-b26e-ac4cbc8a5978', 1, 1, '2026-06-20 16:20:21');

-- ==== processes 子项 ====
INSERT INTO processes (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('15-001', '胶装A4', '本', 1, 8.0, 0, 0, 10.0, 3.0, 2.0, 5, '后道装订员', '装订/胶装/A4', 1.0, 1, 8, 3.0, '', '15', '096e5617-ccd5-4b18-9bb1-c63f9de673bd', 0, 1, '后道装订', '2026-06-20 16:21:04');
INSERT INTO processes (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('15-002', '骑马钉A4', '本', 1, 3.0, 0, 0, 5.0, 1.0, 0.5, 3, '后道装订员', '装订/骑马钉/A4', 1.0, 1, 5, 1.0, '', '15', NULL, 0, 1, '后道装订', '2026-06-20 16:21:04');
INSERT INTO processes (code, name, unit, pricing_tier, sale_price, default_outsource, can_rename, min_charge, alert_price, floor_price, production_score, production_role, stat_tag, stat_coefficient, detail_print, consume_score, cost_price, remark, parent_code, server_spec_id, is_master, is_active, category, created_at) VALUES ('15-003', '圈装A4', '本', 1, 5.0, 0, 0, 8.0, 2.0, 1.0, 4, '后道装订员', '装订/圈装/A4', 1.0, 1, 6, 1.8, '', '15', NULL, 0, 1, '后道装订', '2026-06-20 16:21:04');
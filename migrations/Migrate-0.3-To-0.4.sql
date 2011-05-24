--
-- Migration script from 0.3 to 0.4
--
-- This script must be applied before you restart OpenERP with the new 0.4
-- version. If you updated first, it won't work ! To apply this file, run :
--
--      psql -f Migrate-0.3-To-0.4.sql <database>
--

-- Renamed column 'ref' to 'reference' in rent.order object
ALTER TABLE rent_order RENAME ref TO reference;

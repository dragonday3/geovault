-- 0008: one photo per favourite (uploading again replaces it).
DROP INDEX photos_favourite_idx;
ALTER TABLE photos ADD CONSTRAINT photos_one_per_favourite UNIQUE (favourite_id);

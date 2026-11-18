# Eval changelog

Accepted baselines with before/after metrics.

- 2026-11-18 stage 01 (Creator Radar): spearman 0.853

- 2026-11-18 stage 01 (Creator Radar): spearman 0.853→0.853

- 2026-11-18 stage 02 (Stream Recorder): extract_exact 1.000, extract_p95_s 0.423, disk_ratio 1.050

- 2026-11-18 stage 21 (Storage Lifecycle): deleted_promptly 1.000, disk_growth_ratio 0.860, orphans_left 0.000

- 2026-11-18 stage 03 (Chat Capture): align_within_2s 0.833, align_median_s 0.971, excess_missing_share 0.000

- 2026-11-18 stage 04 (Platform Clips & VOD Ingest): mapped_correct 1.000, mapped_within_1h 1.000, null_offset_trend_only 1.000

- 2026-11-18 stage 05 (Moment Heatmap): recall_at_20 0.983, precision_at_20 0.975, recall_at_20_live 0.933, precision_at_20_live 0.925, fuse_s_per_hour 0.005

- 2026-11-18 stage 07 (Audio Cleanup & Music Removal): detector_accuracy 1.000, skip_when_no_music 1.000, radio_no_longer_matches 1.000, voice_snr_gain_db 12.381

- 2026-11-18 stage 05 (Moment Heatmap): score_s_per_hour 43.271, recall_at_20 0.983→0.983, precision_at_20 0.975→0.975, recall_at_20_live 0.933→0.933, precision_at_20_live 0.925→0.925, fuse_s_per_hour 0.005→0.005

- 2026-11-18 stage 06 (Transcription): wer_en 0.000, wer_es 0.000, wer_pt 0.091, wer_fr 0.000, wer_de 0.000, wer_ru 0.000, wer_tr 0.000, wer_vi 0.080, wer_ar 0.071, wer_ja 0.070, wer_others_max 0.091, wer_others_mean 0.035, timing_median_s 0.019

- 2026-11-18 stage 08 (Game Event Detection): precision_death 1.000, recall_death 1.000, precision_arrest 1.000, recall_arrest 1.000, precision_wanted 1.000, recall_wanted 1.000, precision_mission 1.000, recall_mission 1.000, precision_crash 1.000, recall_crash 1.000, precision_loading 1.000, recall_loading 1.000, precision_menu 1.000, recall_menu 1.000, precision_min_core 1.000, seconds_per_window 2.928

- 2026-11-18 stage 13 (Style Study): cut_rate_rel_err 0.024, caption_y_err 0.003, caps_detected 1.000, fill_color_err 0.016, layout_detected 1.000, split_err 0.009, zoom_rate_abs_err 0.695

- 2026-11-18 stage 09 (Clip Builder): boundary_iou 0.797, payoff_included 0.983, plans_valid 1.000, both_versions 1.000, standalone_openings 1.000

- 2026-11-18 stage 10 (Reframe & Layout): facecam_found 1.000, facecam_false 0.000, subject_in_crop 0.963, caption_clear 1.000, face_in_top_panel 1.000, max_pan_speed_ratio 1.000

- 2026-11-18 stage 11 (Captions & On-screen Text): timing_drift_max_s 0.000, lines_fit 1.000, hook_and_credit 1.000, libass_ok 1.000, profile_driven 1.000

- 2026-11-18 stage 10 (Reframe & Layout): facecam_found 1.000→1.000, facecam_false 0.000→0.000, subject_in_crop 0.963→0.963, caption_clear 1.000→1.000, face_in_top_panel 1.000→1.000, max_pan_speed_ratio 1.000→1.000

- 2026-11-18 stage 10 (Reframe & Layout): facecam_found 1.000→1.000, facecam_false 0.000→0.000, subject_in_crop 0.963→0.963, caption_clear 1.000→1.000, face_in_top_panel 1.000→1.000, max_pan_speed_ratio 1.000→1.000, facecam_in_game_crop 0.146

- 2026-11-18 stage 12 (Render Engine): validation_pass 1.000, platform_fit 1.000, versions_rendered 1.000, render_s_per_40s_linux 57.287

- 2026-11-18 stage 14 (Packaging): within_limits 1.000, language_match 1.000, no_duplicate_titles 1.000, patterns_tracked 1.000, safety_blocks_pii 1.000

- 2026-11-18 stage 15 (Auto-Gate): duplicates_caught 1.000, false_duplicates 0.000, repeat_to_same_account_blocked 1.000, first_post_allowed 1.000, decisions_have_reasons 1.000, blocklist_pulls_everywhere 1.000

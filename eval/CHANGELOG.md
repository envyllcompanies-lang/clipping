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

- 2026-11-18 stage 16 (Publishing (framework + connectors 17-20)): one_clip_every_platform 1.000, no_double_posts 1.000, fallback_tasks_created 1.000, fields_valid 1.000, media_deleted_after_upload 1.000, rate_limit_respected 1.000, spacing_respected 1.000

- 2026-11-18 stage 23 (Dashboard & Kill Switch): alerts_fire 1.000, kill_switch_removes 1.000, undeletable_become_tasks 1.000, screens_within_3_taps 1.000

- 2026-11-18 stage 15 (Auto-Gate): duplicates_caught 1.000→1.000, false_duplicates 0.000→0.000, repeat_to_same_account_blocked 1.000→1.000, first_post_allowed 1.000→1.000, decisions_have_reasons 1.000→1.000, blocklist_pulls_everywhere 1.000→1.000

- 2026-11-18 stage 16 (Publishing (framework + connectors 17-20)): one_clip_every_platform 1.000→1.000, no_double_posts 1.000→1.000, fallback_tasks_created 1.000→1.000, fields_valid 1.000→1.000, media_deleted_after_upload 1.000→1.000, rate_limit_respected 1.000→1.000, spacing_respected 1.000→1.000

- 2026-11-18 stage 27 (Account Provisioning Tool): one_run_creates_everything 1.000, naming_carries_language 1.000, taken_handle_gets_variant 1.000, codes_route_to_right_slot 1.000, no_cross_language_codes 1.000, wrong_account_rejected 1.000, rerun_changes_nothing 1.000

- 2026-11-18 stage 28 (Language Market Ranking): weekly_table_complete 1.000, four_week_streak_required 1.000, recommendation_replaces_lowest 1.000, provisioning_prepped 1.000, shares_follow_scores 1.000, frozen_after_release 1.000

- 2026-11-18 stage 22 (Analytics & Feedback Loop): stats_missing_share 0.000, bandit_finds_best_layout 1.000, worse_refit_refused 1.000, changes_explained 1.000, digest_produced 1.000, score_performance_spearman 0.370, layout_weights_written 1.000

- 2026-11-18 stage 25 (Infrastructure: end-to-end through the queue): end_to_end_ok 1.000, platforms_live 6.000, renders_left_after_upload 0.000

- 2026-11-18 stage 02 (Stream Recorder (real live stream)): recording_started_s 3.003, segments_recorded 8.000, extract_exact 1.000, extract_p95_s 0.284, disk_ratio 1.006

- 2026-11-18 stage 04 (Platform Clips & VOD Ingest (real)): mapped_consistent 1.000, mapped_share_of_resolvable 1.000, null_offset_trend_only 1.000

- 2026-11-18 stage 21 (Storage Lifecycle): deleted_promptly 1.000→1.000, disk_growth_ratio 0.860→0.860, orphans_left 0.000→0.000

- 2026-11-18 stage 03 (Chat Capture (real)): missing_share 0.000, clip_moments_with_spike_10s 0.375, align_within_2s_vs_clip_labels 0.125, align_median_s_vs_clip_labels 6.500

- 2026-11-19 stage 31 (Gameplay Moment Analysis (real VODs)): gameplay_gain_fit_half -0.050, gameplay_gain_test_half -0.012, gameplay_weight_kept 0.000, heatmap_recall_with_gameplay 0.188, heatmap_recall_without 0.175, heatmap_gain_from_gameplay 0.013, calibration_built 1.000

- 2026-11-19 stage 32 (Creator Profile & Reaction (real VODs)): reaction_gain_fit_half 0.013, reaction_gain_test_half 0.025, reaction_weight_kept 0.500, reaction_alone_recall_normalized 0.188, reaction_alone_recall_raw 0.212, normalized_minus_raw -0.025, heatmap_recall_with_reaction 0.175, heatmap_recall_without 0.175, heatmap_gain_from_reaction 0.000

- 2026-11-19 stage 05 (Moment Heatmap (real VODs)): recall_at_20 0.200, precision_at_20 0.463

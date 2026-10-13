# Executed evidence — UIOWA-136 rendered-review replay

This is an actual cloud execution record, not a hosted-CI or human-review claim.

Environment: Python 3.13.5, PyMuPDF 1.26.7, Poppler 25.06.0.

Source Git blobs (the tested bytes):

```text
3a483d44a95e8915785f1aea91782b415863583a  README.md
96dd7d5c5b0b0750f757a9442b6ef0ab1f066ee7  observed_review.json
cca676a23d6a8b83dd3446cb04bff0b3b0e0b7ef  replay_review.py
d0e35315a08158067b03af03402cac20eba7a4b7  reviewed-proposal.pdf
033328ef4e45bed481a8bb933f05108383d5a108  test_render_review.py
```

Actual commands from `render_review/`:

```sh
python -m unittest -v test_render_review
python -O -m unittest -v test_render_review
```

Normal execution, verbatim:

```text
test_changed_but_readable_bytes_do_not_inherit_review (test_render_review.RenderReview.test_changed_but_readable_bytes_do_not_inherit_review) ... ok
test_changed_input_cli_returns_nonzero_even_when_readable (test_render_review.RenderReview.test_changed_input_cli_returns_nonzero_even_when_readable) ... ok
test_destination_below_page_detected (test_render_review.RenderReview.test_destination_below_page_detected) ... ok
test_dropped_navigation_annotation_detected (test_render_review.RenderReview.test_dropped_navigation_annotation_detected) ... ok
test_dropped_outline_detected (test_render_review.RenderReview.test_dropped_outline_detected) ... ok
test_exact_original_provider_bytes (test_render_review.RenderReview.test_exact_original_provider_bytes) ... ok
test_existing_output_is_not_overwritten (test_render_review.RenderReview.test_existing_output_is_not_overwritten) ... ok
test_independent_poppler_opens_and_renders_every_page (test_render_review.RenderReview.test_independent_poppler_opens_and_renders_every_page) ... ok
test_invalid_pdf_cli_returns_error_without_gallery (test_render_review.RenderReview.test_invalid_pdf_cli_returns_error_without_gallery) ... ok
test_link_rectangle_in_blank_space_detected (test_render_review.RenderReview.test_link_rectangle_in_blank_space_detected) ... ok
test_link_rectangle_on_another_real_label_detected (test_render_review.RenderReview.test_link_rectangle_on_another_real_label_detected) ... ok
test_missing_physical_page_detected (test_render_review.RenderReview.test_missing_physical_page_detected) ... ok
test_original_cli_returns_zero (test_render_review.RenderReview.test_original_cli_returns_zero) ... ok
test_placeholder_status_deletion_detected (test_render_review.RenderReview.test_placeholder_status_deletion_detected) ... ok
test_reader_opens_all_nine_pages (test_render_review.RenderReview.test_reader_opens_all_nine_pages) ... ok
test_replay_creates_all_pages_manifest_and_gallery (test_render_review.RenderReview.test_replay_creates_all_pages_manifest_and_gallery) ... ok
test_rerun_never_claims_visual_or_human_approval (test_render_review.RenderReview.test_rerun_never_claims_visual_or_human_approval) ... ok
test_text_crossing_printable_margin_detected (test_render_review.RenderReview.test_text_crossing_printable_margin_detected) ... ok
test_unreasonable_resolution_creates_nothing (test_render_review.RenderReview.test_unreasonable_resolution_creates_nothing) ... ok
test_unresolved_reference_deletion_detected (test_render_review.RenderReview.test_unresolved_reference_deletion_detected) ... ok
test_wrong_attachment_on_same_page_detected (test_render_review.RenderReview.test_wrong_attachment_on_same_page_detected) ... ok
test_wrong_existing_target_page_detected (test_render_review.RenderReview.test_wrong_existing_target_page_detected) ... ok

----------------------------------------------------------------------
Ran 22 tests in 6.268s

OK
```

Optimized execution, verbatim:

```text
test_changed_but_readable_bytes_do_not_inherit_review (test_render_review.RenderReview.test_changed_but_readable_bytes_do_not_inherit_review) ... ok
test_changed_input_cli_returns_nonzero_even_when_readable (test_render_review.RenderReview.test_changed_input_cli_returns_nonzero_even_when_readable) ... ok
test_destination_below_page_detected (test_render_review.RenderReview.test_destination_below_page_detected) ... ok
test_dropped_navigation_annotation_detected (test_render_review.RenderReview.test_dropped_navigation_annotation_detected) ... ok
test_dropped_outline_detected (test_render_review.RenderReview.test_dropped_outline_detected) ... ok
test_exact_original_provider_bytes (test_render_review.RenderReview.test_exact_original_provider_bytes) ... ok
test_existing_output_is_not_overwritten (test_render_review.RenderReview.test_existing_output_is_not_overwritten) ... ok
test_independent_poppler_opens_and_renders_every_page (test_render_review.RenderReview.test_independent_poppler_opens_and_renders_every_page) ... ok
test_invalid_pdf_cli_returns_error_without_gallery (test_render_review.RenderReview.test_invalid_pdf_cli_returns_error_without_gallery) ... ok
test_link_rectangle_in_blank_space_detected (test_render_review.RenderReview.test_link_rectangle_in_blank_space_detected) ... ok
test_link_rectangle_on_another_real_label_detected (test_render_review.RenderReview.test_link_rectangle_on_another_real_label_detected) ... ok
test_missing_physical_page_detected (test_render_review.RenderReview.test_missing_physical_page_detected) ... ok
test_original_cli_returns_zero (test_render_review.RenderReview.test_original_cli_returns_zero) ... ok
test_placeholder_status_deletion_detected (test_render_review.RenderReview.test_placeholder_status_deletion_detected) ... ok
test_reader_opens_all_nine_pages (test_render_review.RenderReview.test_reader_opens_all_nine_pages) ... ok
test_replay_creates_all_pages_manifest_and_gallery (test_render_review.RenderReview.test_replay_creates_all_pages_manifest_and_gallery) ... ok
test_rerun_never_claims_visual_or_human_approval (test_render_review.RenderReview.test_rerun_never_claims_visual_or_human_approval) ... ok
test_text_crossing_printable_margin_detected (test_render_review.RenderReview.test_text_crossing_printable_margin_detected) ... ok
test_unreasonable_resolution_creates_nothing (test_render_review.RenderReview.test_unreasonable_resolution_creates_nothing) ... ok
test_unresolved_reference_deletion_detected (test_render_review.RenderReview.test_unresolved_reference_deletion_detected) ... ok
test_wrong_attachment_on_same_page_detected (test_render_review.RenderReview.test_wrong_attachment_on_same_page_detected) ... ok
test_wrong_existing_target_page_detected (test_render_review.RenderReview.test_wrong_existing_target_page_detected) ... ok

----------------------------------------------------------------------
Ran 22 tests in 6.333s

OK
```

The original PDF was independently rendered by Poppler at 110 DPI; every
physical page was opened as an image by the AI reviewer. The manifest records
the hashes of those nine images. No source-writer modification was needed to
address the inspected sample. No claim is made that arbitrary generated input,
DOCX, the separate 24-page sample, or human accessibility review was completed.

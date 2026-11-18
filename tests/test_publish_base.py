from clipping.publish.base import PostStatus, PublishResult


def test_publish_result_defaults():
    result = PublishResult(status=PostStatus.QUEUED)
    assert result.platform_post_id is None
    assert result.error is None

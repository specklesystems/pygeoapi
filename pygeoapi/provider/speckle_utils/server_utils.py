from typing import Tuple


def get_stream_branch(self: "SpeckleProvider", client: "SpeckleClient", wrapper: "StreamWrapper") -> Tuple:
    """Get stream and branch from the server."""
    
    from specklepy.logging.exceptions import SpeckleException

    branch = None
    stream = client.stream.get(
        id = wrapper.stream_id, branch_limit=100
    )

    if isinstance(stream, Exception):
        raise SpeckleException(stream.message+ ", "+ self.speckle_url)

    for br in stream['branches']['items']:
        if br['id'] == wrapper.model_id:
            branch = br
            break
    return stream, branch
    
def get_client(wrapper: "StreamWrapper", url_proj: str) -> "SpeckleClient":
    """Get unauthenticated SpeckleClient."""

    from specklepy.core.api.client import SpeckleClient

    # get client by URL, no authentication
    client = SpeckleClient(host=wrapper.host, use_ssl=wrapper.host.startswith("https"))
    client.account.serverInfo.url = url_proj.split("/projects")[0]
    return client

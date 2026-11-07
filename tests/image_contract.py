"""Shared expectations for image integration and static tests."""

EXPECTED_USER = "1000:1000"

EXPECTED_PORTS = {
    "audiobookshelf": (8000,),
    "authelia": (9091,),
    "error-pages": (8080,),
    "lldap": (3890, 17170),
}

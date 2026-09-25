"""
Blockchain exceptions for DRF error handling per API_SPECIFICATION.md.
"""
from rest_framework import status
from rest_framework.exceptions import APIException


class BlockchainError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Blockchain transaction failed or timed out."
    default_code = "BLOCKCHAIN_ERROR"


class BlockchainRevertError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Blockchain transaction reverted."
    default_code = "FORBIDDEN"

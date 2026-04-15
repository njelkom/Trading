class DomainError(Exception):
    pass


class AuthenticationError(DomainError):
    """API 인증 실패"""
    pass


class ConnectionError(DomainError):
    """외부 서비스 연결 실패"""
    pass


class AnalysisError(DomainError):
    """AI 분석 처리 실패"""
    pass


class ConfigurationError(DomainError):
    """설정값 누락 또는 잘못된 설정"""
    pass

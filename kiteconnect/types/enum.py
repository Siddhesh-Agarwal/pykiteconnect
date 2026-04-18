from enum import StrEnum


class Product(StrEnum):
    MIS = "MIS"
    CNC = "CNC"
    NRML = "NRML"
    CO = "CO"


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    SLM = "SL-M"
    SL = "SL"


class Variety(StrEnum):
    REGULAR = "regular"
    CO = "co"
    AMO = "amo"
    ICEBERG = "iceberg"
    AUCTION = "auction"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Validity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"
    TTL = "TTL"


class PositionType(StrEnum):
    DAY = "day"
    OVERNIGHT = "overnight"


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    CDS = "CDS"
    BFO = "BFO"
    MCX = "MCX"
    BCD = "BCD"


class MarginSegment(StrEnum):
    EQUITY = "equity"
    COMMODITY = "commodity"


class Status(StrEnum):
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class GTTType(StrEnum):
    OCO = "two-leg"
    SINGLE = "single"


class GTTStatus(StrEnum):
    ACTIVE = "active"
    TRIGGERED = "triggered"
    DISABLED = "disabled"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    DELETED = "deleted"

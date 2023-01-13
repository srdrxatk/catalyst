import pytest

from brownie import convert, ZERO_ADDRESS
from brownie import Token
from math import log2, ceil
import numpy as np


def evmBytes32ToAddress(bytes32):
    return convert.to_address(bytes32[12:])


# Decode a Catalyst message in Python with Brownie.
@pytest.fixture(scope="session")
def decodePayload():
    def _decodePayload(data, decode_address=evmBytes32ToAddress):
        context = data[0]
        if context & 1:
            return {
                "_context": data[0],
                "_fromPool": decode_address(data[1:33]),
                "_toPool": decode_address(data[33:65]),
                "_who": decode_address(data[65:97]),
                "_LU": convert.to_uint(data[97:129]),
                "_minOut": convert.to_uint(data[129:161]),
                "_escrowAmount": convert.to_uint(data[161:193])
            }
        customDataLength = convert.to_uint(data[226:228], type_str="uint16")
        return {
            "_context": data[0],
            "_fromPool": decode_address(data[1:33]),
            "_toPool": decode_address(data[33:65]),
            "_who": decode_address(data[65:97]),
            "_U": convert.to_uint(data[97:129]),
            "_assetIndex": convert.to_uint(data[129], type_str="uint8"),
            "_minOut": convert.to_uint(data[130:162]),
            "_escrowAmount": convert.to_uint(data[162:194]),
            "_escrowToken": decode_address(data[194:226]),
            "customDataLength": customDataLength,
            "_customDataTarget": decode_address(data[228:260]) if customDataLength > 0 else None,
            "_customData": data[260:260+customDataLength - 32] if customDataLength > 0 else None
        }
    
    yield _decodePayload


# Construct a Catalyst message in Python with Brownie.
@pytest.fixture(scope="session")
def payloadConstructor():
    def _payloadConstructor(
    _from,
    _to,
    _who,
    _U,
    _assetIndex=0,
    _minOut=0,
    _escrowAmount=0,
    _escrowToken=ZERO_ADDRESS,
    _context=convert.to_bytes(0, type_str="bytes1"),
):
        return (
            _context
            + convert.to_bytes(_from, type_str="bytes32")
            + convert.to_bytes(_to, type_str="bytes32")
            + _who
            + convert.to_bytes(_U, type_str="bytes32")
            + convert.to_bytes(_assetIndex, type_str="bytes1")
            + convert.to_bytes(_minOut, type_str="bytes32")
            + convert.to_bytes(_escrowAmount, type_str="bytes32")
            + convert.to_bytes(_escrowToken, type_str="bytes32")
            + convert.to_bytes(0, type_str="bytes2")
        )  
    
    yield _payloadConstructor
    

# Construct a Catalyst message in Python with Brownie.
@pytest.fixture(scope="session")
def LiquidityPayloadConstructor():
    def _liquidityPayloadConstructor(
        _from,
        _to,
        _who,
        _U,
        _minOut=0,
        _escrowAmount=0,
        _context=convert.to_bytes(1, type_str="bytes1")
    ):
        return (
            _context
            + convert.to_bytes(_from, type_str="bytes32")
            + convert.to_bytes(_to, type_str="bytes32")
            + _who
            + convert.to_bytes(_U, type_str="bytes32")
            + convert.to_bytes(_minOut, type_str="bytes32")
            + convert.to_bytes(_escrowAmount, type_str="bytes32")
            + convert.to_bytes(0, type_str="bytes2")
    )
    
    yield _liquidityPayloadConstructor


@pytest.fixture(scope="session")
def relative_error():
    def _relative_error(a, b):
        if a is None or b is None:
            return None
        
        if a == 0 and b == 0:
            return 0

        return 2*(a - b)/(abs(a) + abs(b))

    yield _relative_error


@pytest.fixture(scope="session")
def assert_relative_error(relative_error):
    def _assert_relative_error(a, b, neg_error_bound, pos_error_bound, error_id=None):
        
        error = relative_error(a, b)
        error_id_string = f"(ERR: {error_id})" if error_id is not None else ""
        assert neg_error_bound <= error <= pos_error_bound, f"Error {error} is outside allowed range [{neg_error_bound}, {pos_error_bound}] {error_id_string}"

    yield _assert_relative_error


@pytest.fixture(scope="session")
def assert_abs_relative_error(assert_relative_error):
    def _assert_abs_relative_error(a, b, error_bound, error_id=None):
        assert_relative_error(a, b, -error_bound, error_bound, error_id)

    yield _assert_abs_relative_error
    

@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def compute_expected_swap():
    # The below functions are implemented exactly instead of through the mathematical implementation.
    def _compute_expected_swap(swap_amount, fromToken, toToken, fromSwappool, toSwappool=None, withU=False):
        if toSwappool is None:
            toSwappool = fromSwappool
        
        amp = 2**64
        try:
            amp = fromSwappool._amp()
        except AttributeError:
            pass
        
        w1 = fromSwappool._weight(fromToken)
        w2 = toSwappool._weight(toToken)
        a = fromToken.balanceOf(fromSwappool)
        b = toToken.balanceOf(toSwappool)
        if amp != 2**64:
            a *= w1
            b *= w2
            swap_amount *= w1
            amp /= 2**64
            
            bamp = b**(1-amp)
            
            U = (a + swap_amount)**(1-amp) - (a)**(1-amp)
            if withU:
                return (U*2**64, ceil(b/w2 * (1 - ((bamp - U)/(bamp))**(1/(1-amp)))))
            return ceil(b/w2 * (1 - ((bamp - U)/(bamp))**(1/(1-amp))))
        
        if w1 == w2:
            return ceil((b*swap_amount)/(a+swap_amount))
        U = w1 * log2((a + swap_amount)/a)
        if withU:
            return (U*2**64, ceil(b * (1 - 2**(-U/w2))))
        return ceil(b * (1 - 2**(-U/w2)))
        
    yield _compute_expected_swap


@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def compute_expected_swap_given_U():
    # The below functions are implemented exactly instead of through the mathematical implementation.
    def _compute_expected_swap_given_U(U, toToken, toSwappool):
        amp = 2**64
        try:
            amp = toSwappool._amp()
        except AttributeError:
            pass
        
        w = toSwappool._weight(toToken)
        b = toToken.balanceOf(toSwappool)
        U /= 2**64
        if amp != 2**64:
            b *= w
            amp /= 2**64
            
            bamp = b**(1-amp)
            
            return ceil(b/w * (1 - ((bamp - U)/(bamp))**(1/(1-amp))))
        
        
        return ceil(b * (1 - 2**(-U/w)))
        
    yield _compute_expected_swap_given_U


@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def compute_withdraw_to_U(get_pool_tokens, balance_0):
    # The below functions are implemented exactly instead of through the mathematical implementation.
    def _compute_withdraw_to_U(withdraw_amount, swappool):
        amp = 2**64
        try:
            amp = swappool._amp()
        except AttributeError:
            pass
        
        totalSupply = swappool.totalSupply()
        tokens = get_pool_tokens(swappool)
        if amp != 2**64:
            walpha = balance_0(swappool)
            
            N = len(tokens)
            OneMinusAmp = (2**64-amp)/2**64
            return ceil((N * walpha**OneMinusAmp * ((1+ withdraw_amount/totalSupply)**OneMinusAmp - 1)) * 2**64)
        
        wsum = sum([swappool._weight(token) for token in tokens])
        return ceil(log2(totalSupply/(totalSupply-withdraw_amount))*wsum * 2**64)
        
    yield _compute_withdraw_to_U


@pytest.fixture(scope="session")
def prod():
    def _prod(arr):
        product = 1
        for a in arr:
            product *= a
        return product

    yield _prod


@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def invariant(get_pool_tokens, prod):
    def _invariant(swappool):
        tokens = get_pool_tokens(swappool)
        amp = 2**64
        try:
            amp = swappool._amp()
        except AttributeError:
            pass
    
        weights = np.array([swappool._weight(token) for token in tokens])
        balances = np.array([token.balanceOf(swappool) for token in tokens])
        if amp != 2**64:
            oneMinusAmp = (2**64 - amp)/2**64
            return ((weights * balances)**oneMinusAmp).sum()
        
        return (balances**weights).prod()

    yield _invariant


@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def balance_0(get_pool_tokens, invariant):
    def _balance_0(swappool):
        tokens = get_pool_tokens(swappool)
        amp = swappool._amp()
        assert amp != 2**64
        
        walpha_theta = (invariant(swappool) - swappool._unitTracker()/2**64)/len(tokens)
        
        return int(np.power(walpha_theta, (2**64/(2**64-amp))))
    
    yield _balance_0


@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def compute_expected_liquidity_swap(get_pool_tokens):
    # The below functions are implemented exactly instead of through the mathematical implementation.
    def _compute_expected_liquidity_swap(swap_amount, fromSwappool, toSwappool, withU=False):
        fromTokens = get_pool_tokens(fromSwappool)
        toTokens = get_pool_tokens(toSwappool)
        
        amp = 2**64
        try:
            amp = fromSwappool._amp()
        except AttributeError:
            pass
        
        fromPT = fromSwappool.totalSupply()
        toPT = toSwappool.totalSupply()
        pt = swap_amount
        
        if amp != 2**64:
            oneMinusAmp = (2**64 - amp)/2**64
            a0 = balance_0(fromSwappool)
            b0 = balance_0(toSwappool)
            
            
            U = ((a0 + (a0 * pt)/fromPT)**(oneMinusAmp) - (a0)**(oneMinusAmp)) * len(fromTokens)
            wpt = (b0**(oneMinusAmp) + U/len(toTokens))**(2**64/(2**64-amp)) - b0
            
            if withU:
                return (U, wpt*toPT/b0)
            return wpt*toPT/b0
        
        fromWSUM = sum([fromSwappool._weight(token) for token in fromTokens])
        toWSUM = sum([toSwappool._weight(token) for token in toTokens])
        U = log2(fromPT/(fromPT-pt)) * fromWSUM
        
        share = 1 - 2**(-U/toWSUM)
        if withU:
            return (U, toPT * (share/(1-share)))
        return toPT * (share/(1-share))
        
    yield _compute_expected_liquidity_swap
    
    
@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def get_pool_tokens():
    def _get_pool_tokens(swappool):
        tokens = []
        while len(tokens) < 3:
            token = swappool._tokenIndexing(len(tokens))
            if token != ZERO_ADDRESS:
                tokens.append(Token.at(token))
            else:
                break
        
        return tokens
    
    yield _get_pool_tokens


@pytest.mark.no_call_coverage
@pytest.fixture(scope="session")
def compute_expected_units_capacity():
    def _compute_expected_units_capacity(
        ref_capacity,
        ref_capacity_timestamp,
        change_timestamp,
        change_capacity_delta,
        current_timestamp,
        max_capacity,
        decayrate=24*60*60
    ):
        # Since the units capacity is time dependant, two events must be taken into account:
        #   - The capacity change since the ref_capacity value was taken until the capacity was modified by a transaction (the change_timestamp and change_capacity_delta)
        #   - The capacity change since the transaction until now

        # Compute the capacity at the time of the change
        ref_capacity_at_change = min(max_capacity, ref_capacity + int(max_capacity*(change_timestamp - ref_capacity_timestamp)/decayrate))

        # Compute the capacity after the change
        change_capacity = max(0, min(max_capacity, ref_capacity_at_change + change_capacity_delta))

        # Compute the capacity at the current time
        return min(max_capacity, change_capacity + int(max_capacity*(current_timestamp - change_timestamp)/decayrate))

    yield _compute_expected_units_capacity
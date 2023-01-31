import pytest
from brownie import reverts, convert, web3
from brownie.test import given, strategy


pytestmark = pytest.mark.usefixtures("group_finish_setup", "group_connect_pools")

#TODO add fees test (create fixture that sets up non-zero fees to the pool)

@pytest.mark.no_call_coverage
@given(swap_percentage=strategy("uint256", max_value=1*10**18))
def test_cross_pool_swap(
    channel_id,
    pool_1,
    pool_2,
    pool_1_tokens,
    pool_2_tokens,
    berg,
    deployer,
    ibc_emulator,
    compute_expected_swap,
    swap_percentage
):
    swap_percentage /= 10**18
    #TODO parametrize source_token and target_tokens?
    source_token = pool_1_tokens[0]
    target_token = pool_2_tokens[0]
    swap_amount = int(source_token.balanceOf(pool_1) * swap_percentage)

    assert target_token.balanceOf(berg) == 0

    source_token.transfer(berg, swap_amount, {'from': deployer})
    source_token.approve(pool_1, swap_amount, {'from': berg})
    
    try:
        y = compute_expected_swap(swap_amount, source_token, target_token)['output']
    except:
        pytest.skip()   #TODO For certain pool configs, there is no output for the specified swap amount (swap too large) => remove this workaround + be specific on the test configs to 'skip'
    
    tx = pool_1.swapToUnits(
        channel_id,
        convert.to_bytes(pool_2.address.replace("0x", "")),
        convert.to_bytes(berg.address.replace("0x", "")),
        source_token,
        0,
        swap_amount,
        0,
        berg,
        {"from": berg},
    )
    assert source_token.balanceOf(berg) == 0
    
    # The swap may revert because of the security limit     #TODO mark these cases as 'skip'?
    if pool_2.getUnitCapacity() < pool_2.dry_swap_from_unit(pool_2._tokenIndexing(0), tx.events["SwapToUnits"]["output"]) * pool_2._weight(pool_2._tokenIndexing(0)):
        with reverts("Swap exceeds security limit"):
            txe = ibc_emulator.execute(tx.events["IncomingMetadata"]["metadata"][0], tx.events["IncomingPacket"]["packet"], {"from": berg})
        return
    else:
        txe = ibc_emulator.execute(tx.events["IncomingMetadata"]["metadata"][0], tx.events["IncomingPacket"]["packet"], {"from": berg})
    
    purchased_tokens = txe.events["SwapFromUnits"]["output"]
    
    assert purchased_tokens == target_token.balanceOf(berg)

    # Make sure no more than it's theoretically due is given
    assert purchased_tokens <= y + 5 or purchased_tokens <= int(y*1.000001), "Swap returns more than theoretical"       #TODO set bound as test variable?

    # Make sure no much less than it's theoretically due is given (ignore check for very small swaps)
    if swap_amount > 1000:
        assert purchased_tokens >= y - 1 or purchased_tokens >= int(y*9/10), "Swap returns much less than theoretical"  #TODO set bound as test variable?


#TODO add test that empties the pool



@pytest.mark.no_call_coverage
@given(swap_percentage=strategy("uint256", max_value=5*10**17))
def test_cross_pool_swap_min_out(
    channel_id,
    pool_1,
    pool_2,
    pool_1_tokens,
    pool_2_tokens,
    berg,
    deployer,
    compute_expected_swap,
    ibc_emulator,
    swap_percentage
):
    swap_percentage /= 10**18
    
    source_token = pool_1_tokens[0]
    target_token = pool_2_tokens[0]
    
    swap_amount = int(source_token.balanceOf(pool_1) * swap_percentage)

    assert target_token.balanceOf(berg) == 0

    source_token.transfer(berg, swap_amount, {'from': deployer})
    source_token.approve(pool_1, swap_amount, {'from': berg})
    
    try:
        y = compute_expected_swap(swap_amount, source_token, target_token)['output']
    except:
        pytest.skip()   #TODO For certain pool configs, there is no output for the specified swap amount (swap too large) => remove this workaround + be specific on the test configs to 'skip'
    
    # Make sure the swap always fails
    if y < 1000:
        min_out = int(y * 2)  # Allow for a greater margin for small y
    else:
        min_out = int(y * 1.2)
    
    tx = pool_1.swapToUnits(
        channel_id,
        convert.to_bytes(pool_2.address.replace("0x", "")),
        convert.to_bytes(berg.address.replace("0x", "")),
        source_token,
        0,
        swap_amount,
        min_out,
        berg,
        {"from": berg},
    )

    assert source_token.balanceOf(berg) == 0

    if min_out == 0:
        return

    with reverts("Insufficient Return"):
        ibc_emulator.execute(tx.events["IncomingMetadata"]["metadata"][0], tx.events["IncomingPacket"]["packet"], {"from": berg})


def test_swap_to_units_event(
    channel_id,
    pool_1,
    pool_2,
    pool_1_tokens,
    berg,
    elwood,
    deployer
):
    """
        Test the SwapToUnits event gets fired.
    """

    swap_amount = 10**8
    min_out     = 100
    
    source_token = pool_1_tokens[0]

    source_token.transfer(berg, swap_amount, {'from': deployer})
    source_token.approve(pool_1, swap_amount, {'from': berg})
    
    tx = pool_1.swapToUnits(
        channel_id,
        convert.to_bytes(pool_2.address.replace("0x", "")),
        convert.to_bytes(elwood.address.replace("0x", "")),     # NOTE: not using the same account as the caller of the tx to make sure the 'targetUser' is correctly reported
        source_token,
        1,                                                      # NOTE: use non-zero target asset index to make sure the field is set on the event (and not just left blank)
        swap_amount,
        min_out,
        elwood,
        {"from": berg},
    )

    observed_units = tx.return_value
    expected_message_hash = web3.keccak(tx.events["IncomingPacket"]["packet"][3]).hex()   # Keccak of the payload contained on the ibc packet

    swap_to_units_event = tx.events['SwapToUnits']

    assert swap_to_units_event['targetPool']   == pool_2
    assert swap_to_units_event['targetUser']   == elwood
    assert swap_to_units_event['fromAsset']    == source_token
    assert swap_to_units_event['toAssetIndex'] == 1
    assert swap_to_units_event['input']        == swap_amount
    assert swap_to_units_event['output']       == observed_units
    assert swap_to_units_event['minOut']       == min_out
    assert swap_to_units_event['messageHash']  == expected_message_hash


def test_swap_from_units_event(
    channel_id,
    pool_1,
    pool_2,
    pool_1_tokens,
    pool_2_tokens,
    berg,
    elwood,
    deployer,
    ibc_emulator
):
    """
        Test the SwapToUnits event gets fired.
    """

    swap_amount = 10**8

    source_token = pool_1_tokens[0]
    target_token = pool_2_tokens[0]

    source_token.transfer(berg, swap_amount, {'from': deployer})
    source_token.approve(pool_1, swap_amount, {'from': berg})
    
    tx = pool_1.swapToUnits(
        channel_id,
        convert.to_bytes(pool_2.address.replace("0x", "")),
        convert.to_bytes(elwood.address.replace("0x", "")),
        source_token,
        0,
        swap_amount,
        0,
        elwood,
        {"from": berg},
    )

    observed_units = tx.return_value
    expected_message_hash = web3.keccak(tx.events["IncomingPacket"]["packet"][3]).hex()   # Keccak of the payload contained on the ibc packet

    txe = ibc_emulator.execute(tx.events["IncomingMetadata"]["metadata"][0], tx.events["IncomingPacket"]["packet"], {"from": berg})

    swap_from_units_event = txe.events['SwapFromUnits']

    assert swap_from_units_event['who']         == elwood
    assert swap_from_units_event['toAsset']     == target_token
    assert swap_from_units_event['input']       == observed_units
    assert swap_from_units_event['output']      == target_token.balanceOf(elwood)
    assert swap_from_units_event['messageHash'] == expected_message_hash

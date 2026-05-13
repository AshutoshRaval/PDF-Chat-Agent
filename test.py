# def computeMinDeliveryTime(requestedHubs, transitionTime):
#     m = len(transitionTime)
#     prefix = [0] * (m + 1)
#     for i in range(m):
#         prefix[i+1] = prefix[i] + transitionTime[i]
#     total = prefix[m]
    
#     current = 1
#     result = 0
    
#     for hub in requestedHubs:
#         if hub == current:
#             continue
#         if hub > current:
#             cw = prefix[hub-1] - prefix[current-1]
#         else:
#             cw = prefix[m] - prefix[current-1] + prefix[hub-1]
        
#         ccw = total - cw
#         result += min(cw, ccw)
#         current = hub
    
#     return result

# # Test Execution
# test_cases = [
#     {"hubs": [3, 1], "times": [10, 10, 10, 10], "expected": 40},
#     {"hubs": [3], "times": [2, 2, 100], "expected": 4},
#     {"hubs": [1, 2, 2, 3], "times": [5, 5, 5], "expected": 10},
#     {"hubs": [5, 2], "times": [10, 10, 10, 10, 10], "expected": 30},
# ]

# for i, tc in enumerate(test_cases):
#     res = computeMinDeliveryTime(tc["hubs"], tc["times"])
#     status = "PASS" if res == tc["expected"] else f"FAIL (Got {res})"
#     print(f"Test Case {i+1}: {status}")



# def computeMinDeliveryTime(requestedHubs, transitionTime):
#     m = len(transitionTime)
#     total = sum(transitionTime)
#     current = 1
#     result = 0
#     for hub in requestedHubs:
#         if hub == current:
#             continue
#         cw = 0
#         steps = (hub - current) % m
#         for k in range(steps):
#             cw += transitionTime[(current - 1 + k) % m]
#         ccw = total - cw
#         result += min(cw, ccw)
#         current = hub
#     return result


def computeMinDeliveryTime(deliverySequence, hubTransitionTimes):
    m = len(hubTransitionTimes)
    prefix = [0] * (m + 1)
    for i in range(m):
        prefix[i + 1] = prefix[i] + hubTransitionTimes[i]
    total = prefix[m]
    current = 1
    result = 0
    for hub in deliverySequence:
        if hub == current:
            continue
        if hub > current:
            cw = prefix[hub - 1] - prefix[current - 1]
        else:
            cw = prefix[m] - prefix[current - 1] + prefix[hub - 1]
        result += min(cw, total - cw)
        current = hub
    return result


tests = [
    # (requestedHubs, transitionTime, expected, description)
    ([2,3,3,1],  [3,2,1],      6,  "Sample Case 0 from problem"),
    ([1],        [5,5,5],      0,  "Visit starting hub only — no movement"),
    ([1,2,3,4,5],[1,1,1,1,1], 4,  "Visit all hubs in order, uniform costs"),
    ([5,4,3,2,1],[1,1,1,1,1], 5,  "Visit hubs in reverse order"),
    ([3],        [10,1,10],   10,  "CCW cheaper: 1->3 cw=11, ccw=10"),
    ([2],        [1,100,100],  1,  "Direct neighbor, single hop"),
    ([3,1],      [5,5,5],     10,  "Equidistant both ways each step"),
    ([2,2,2],    [3,3,3],      3,  "Revisit same hub repeatedly after first"),
    ([4,2],      [1,1,1,10],   5,  "Wrap-around expensive: 1->4=3, 4->2 ccw=2"),
]

passed = 0
for rh, tt, exp, desc in tests:
    got = computeMinDeliveryTime(rh, tt)
    status = "PASS" if got == exp else "FAIL"
    if got == exp: passed += 1
    print(f"[{status}] {desc}")
    if got != exp:
        print(f"       requestedHubs={rh}, transitionTime={tt}")
        print(f"       expected={exp}, got={got}")

print(f"\n{passed}/{len(tests)} passed")
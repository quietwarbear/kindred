"""Retired direct-Stripe subscription setup entrypoint.

Kindred subscriptions are configured in RevenueCat Billing. Stripe remains the
RevenueCat payment gateway and still supports Kindred's unrelated contribution
and add-on flows, but application operators must not create a parallel Stripe
Billing subscription catalog with this repository.
"""

import sys


def main() -> int:
    print(
        "Direct Stripe subscription setup is retired. "
        "Configure and verify products, packages, offerings, prices, intervals, "
        "and entitlements in RevenueCat Billing."
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

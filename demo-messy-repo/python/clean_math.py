"""Small pure helpers (control file: nothing here should be reported)."""


def mean(values):
    return sum(values) / len(values)


def variance(values):
    average = mean(values)
    return sum((v - average) ** 2 for v in values) / len(values)


def total(values):
    result = 0
    for value in values:
        result += value
    return result


def product(values):
    result = 1
    for value in values:
        result *= value
    return result


def main():
    print(mean([1, 2]), variance([1, 2]), total([1, 2]), product([1, 2]))


if __name__ == "__main__":
    main()

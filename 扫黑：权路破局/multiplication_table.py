def print_multiplication_table():
    for i in range(1, 10):
        for j in range(1, i + 1):
            print(f"{j}x{i}={i*j}", end="\t")
        print()

if __name__ == "__main__":
    print_multiplication_table()

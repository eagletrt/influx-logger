import sys
import os
from test_report.performances import Performances


def main():
    args = sys.argv[1:]
    if len(args) != 1:
        performances = Performances.load_from_file()
    elif os.path.isfile(args[0]):
        print(f"Loading performances from file: {args[0]}")
        performances = Performances.load_from_file(args[0])
    else:
        print(f"File {args[0]} does not exist.")
        return
    #for name, performance in performances.performances.items():
    #    print(f"\n{name}:\n{performance}")
    #performances.plot_all(save=False, cols=4)
    performances.plot_overall(file_to_save=None)
    print(performances)

if __name__ == "__main__":
    main()

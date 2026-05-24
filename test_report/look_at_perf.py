from test_report.performances import Performances


def main():
    performances = Performances.load_from_file()
    #for name, performance in performances.performances.items():
    #    print(f"\n{name}:\n{performance}")
    #performances.plot_all(save=False)
    performances.plot_overall(file_to_save=None)
    print(performances)

if __name__ == "__main__":
    main()

import os
import pandas as pd
import datetime as dt
import numpy as np
import subprocess
import shutil
from io import BytesIO
from PyQt5.QtWidgets import QMessageBox

from i18n import tr


# matplotlib and docx2pdf are imported on first use, not at module import.
# Importing pyplot builds matplotlib's font cache, which in a frozen app costs
# several seconds on *every* launch - paid before the window ever appeared,
# even though nothing plots until invoices are generated.
plt = None
DateFormatter = None
MonthLocator = None


def _ensure_plotting():
    """Import matplotlib on demand and pin the headless backend."""
    global plt, DateFormatter, MonthLocator
    if plt is not None:
        return
    import matplotlib
    matplotlib.use("Agg")                       # must precede the pyplot import
    import matplotlib.pyplot as _plt
    from matplotlib.dates import DateFormatter as _DateFormatter, MonthLocator as _MonthLocator
    plt, DateFormatter, MonthLocator = _plt, _DateFormatter, _MonthLocator


def check_doubles(invoices):
    debit = invoices[(invoices["Dokumenttyp"] == "Rechnung")]
    transfer = invoices[(invoices["Dokumenttyp"] == "Gutschrift")|(invoices["Dokumenttyp"] == "Information")]
    debitdoubles = debit["Empfänger Name"][debit["Empfänger Name"].isin(transfer["Empfänger Name"])].index
    transferdoubles = transfer["Empfänger Name"][transfer["Empfänger Name"].isin(debit["Empfänger Name"])].index
    doublesprocess = {"Name":[],"Debit":[],"Transfer":[],"Type":[],"Final":[]}
    for i,j in zip(debitdoubles,transferdoubles):
        doublesprocess["Name"].append(debit.loc[i,"Empfänger Name"])
        doublesprocess["Debit"].append(debit.loc[i,"Pos. Bruttobetrag"])
        doublesprocess["Transfer"].append(transfer.loc[j,"Pos. Bruttobetrag"])
        if debit.loc[i,'Pos. Bruttobetrag'] < transfer.loc[j,'Pos. Bruttobetrag']:
            finalsum = transfer.loc[j,'Pos. Bruttobetrag'] - debit.loc[i,'Pos. Bruttobetrag']
            # transfer.loc[j, 'Pos. Bruttobetrag'] = finalsum
            # debit = debit.drop(i)
            doublesprocess["Type"].append("Überweisung")
            doublesprocess["Final"].append(finalsum)

        else:
            finalsum = debit.loc[i,'Pos. Bruttobetrag'] - transfer.loc[j,'Pos. Bruttobetrag']
            # debit.loc[i, 'Pos. Bruttobetrag'] = finalsum
            # transfer = transfer.drop(j)
            doublesprocess["Type"].append("Lastschrift")
            doublesprocess["Final"].append(finalsum)

    return debit,transfer, doublesprocess



def produce_sepa_export_dfs(invoices_selected_persons,EEG_name):
    debit,transfer, doublesprocess = check_doubles(invoices_selected_persons)

    def create_one_line_debit(invoicelistline,EEG_name,datatype = "debit"):
        print(invoicelistline["Empfänger Name"])
        columns_debit_export = ['Fälligkeitsdatum', 'Zahlungspflichtiger Name',
       'Zahlungspflichtiger Adresse', 'Zahlungspflichtiger Ort',
       'Zahlungspflichtiger IBAN', 'Zahlungspflichtiger BIC', 'Betrag in EUR',
       'Zahlungsreferenz/Verwendungszweck', 'Auftraggeberinformation',
       'Geschäftsvorfallcode', 'Auftraggeber IBAN',
       'Abweichender Auftraggeber', 'Mandatsausstellungsdatum', 'Creditor ID',
       'Mandatsreferenz', 'Art der Verwendung', 'Firmenlastschrift']

        columns_transfer_export = ['Durchführungsdatum', 'Empfänger Name', 'Empfänger Adresse',
       'Empfänger Ort', 'Empfänger IBAN', 'Empfänger BIC', 'Betrag in EUR',
       'Zahlungsreferenz/Verwendungszweck', 'Auftraggeberinformation',
       'Geschäftsvorfallcode', 'Dringlichkeit', 'Auftraggeber IBAN',
       'Abweichender Auftraggeber']
        if datatype == "debit":
            exportline = pd.Series([""] * len(columns_debit_export), index=columns_debit_export)
            exportline["Fälligkeitsdatum"] = dt.datetime.today().strftime("%d.%m.%Y")
            matchingdictinvoice = {
                "Zahlungspflichtiger Name": "Empfänger Name",
                "Zahlungspflichtiger Adresse": "Empfänger Adresse 1",
                "Zahlungspflichtiger Ort": "Empfänger Adresse 2",
                "Zahlungspflichtiger IBAN": "Empfänger Konto IBAN",
                "Betrag in EUR": "Pos. Bruttobetrag",
                "Auftraggeber IBAN": "Ersteller IBAN",
                "Mandatsausstellungsdatum":"Empfänger Mandatsausstellung",
                "Mandatsreferenz": "Empfänger Mandatsreferenz",
                "Creditor ID": "Ersteller Creditor Id"
            }
            # exportline["Mandatsreferenz"] = f"{invoicelistline['Empfänger Mitgliedsnummer']:03}"
            # exportline["Creditor ID"] = creditor_ID


            # mandateline = mandates.data[(mandates.data["Vorname"] == invoicelistline["Empfänger Vorame"])]
            # matchingmandate = True
            # if not pd.isna(invoicelistline["Empfänger Nachname"]):
            #     mandateline = mandateline[(mandateline["Nachname"] == invoicelistline["Empfänger Nachname"])]
            # if mandateline.size > 0:
            #     exportline["Mandatsausstellungsdatum"] = mandateline["Mandatsausstellungsdatum"].iloc[0].strftime("%d.%m.%Y")
            #     exportline["Firmenlastschrift"] = mandateline["Firmenlastschrift"].iloc[0]
            # else:
            #     exportline["Creditor ID"] = 0
            #     matchingmandate = False


        elif datatype == "transfer":
            exportline = pd.Series([""] * len(columns_transfer_export), index=columns_transfer_export)
            exportline["Durchführungsdatum"] = dt.datetime.today().strftime("%d.%m.%Y")
            matchingdictinvoice = {
                "Empfänger Name": "Empfänger Name",
                "Empfänger Adresse": "Empfänger Adresse 1",
                "Empfänger Ort": "Empfänger Adresse 2",
                "Empfänger IBAN": "Empfänger Konto IBAN",
                "Betrag in EUR": "Pos. Bruttobetrag",
                "Auftraggeber IBAN": "Ersteller IBAN"
            }

        for exportcol in matchingdictinvoice.keys():
            thisentry = invoicelistline[matchingdictinvoice[exportcol]]

            try:
                thisentry = thisentry.strftime("%d.%m.%Y")
            except: pass
            exportline[exportcol] = thisentry
        if invoicelistline["Empfänger Einzugsart"] == "B2B":
            exportline["Firmenlastschrift"] = 1
        else:
            exportline["Firmenlastschrift"] = 0


        def get_quartal_out_of_str(string):
            y = (string.split("-"))
            return y[1], y[2]

        year, quartal = get_quartal_out_of_str(invoicelistline["Abrechnung"])
        exportline["Zahlungsreferenz/Verwendungszweck"] = f"{EEG_name} Rechung {year} Quartal {quartal}"

        return exportline

    if debit.size > 0:
        serieslist = []
        # missingmandates = []
        for index, line in debit.iterrows():
            exportline = create_one_line_debit(line,EEG_name,datatype="debit")
            if exportline is not None:
                serieslist.append(exportline)
                # if not matchingmandate:
                #     missingmandates.append(f"{line['Empfänger Vorame']} {line['Empfänger Nachname']}")
        debitexport = pd.concat(serieslist, axis=1).T
    else:
        debitexport = None

    if transfer.size > 0:
        serieslist = []
        for index, line in transfer.iterrows():
            exportline = create_one_line_debit(line,EEG_name,datatype="transfer")
            if exportline is not None:
                serieslist.append(exportline)
        transferexport = pd.concat(serieslist, axis=1).T
    else:
        transferexport = None

    reply = QMessageBox.question(None,
        tr('Frage'),
        tr('Willst du jede Positionen einzeln ausweisen \n(z.b. eine eigene Überweisung für '
           'Mitgliedsbeitrag und Stromkosten)??'),
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )

    # Check the user's response
    if reply == QMessageBox.No:
        print("Merge single positions")

        def group_and_aggregate(df, group_cols, sum_cols):
            # Create a dictionary for aggregation:
            # - 'sum' for the columns you want to sum
            # - 'first' for the other columns
            agg_dict = {col: 'sum' for col in sum_cols}  # Sum columns
            other_cols = [col for col in df.columns if col not in group_cols + sum_cols]
            agg_dict.update({col: 'first' for col in other_cols})  # First entry for the rest

            grouped_df = df.groupby(group_cols, as_index=False).agg(agg_dict)

            return grouped_df
        if debitexport is not None:
            debitexport = group_and_aggregate(debitexport,["Zahlungspflichtiger Name"],['Betrag in EUR'])
        if transferexport is not None:
            transferexport = group_and_aggregate(transferexport,["Empfänger Name"],['Betrag in EUR'])

        if (debitexport is not None) and (transferexport is not None):
            doubles_names = debitexport[debitexport['Zahlungspflichtiger Name'].isin(transferexport['Empfänger Name'])]['Zahlungspflichtiger Name']
            for double_name in doubles_names:
                print(double_name)
                diff = debitexport.loc[debitexport['Zahlungspflichtiger Name'] == double_name, 'Betrag in EUR'].values[0] -transferexport.loc[transferexport['Empfänger Name'] == double_name, 'Betrag in EUR'].values[0]
                # if diff > 0  --> more debit than transfer
                if diff > 0:
                    print("We have more debit than transfer")
                    debitexport.loc[debitexport['Zahlungspflichtiger Name'] == double_name, 'Betrag in EUR'] = diff
                    transferexport = transferexport.loc[~(transferexport['Empfänger Name'] == double_name),:].reset_index(drop=True)

                else:
                    print("We have more transfer than debit")
                    transferexport.loc[transferexport['Empfänger Name'] == double_name, 'Betrag in EUR'] = -diff
                    debitexport = debitexport.loc[~(debitexport['Zahlungspflichtiger Name'] == double_name),:].reset_index(drop=True)






    else:
        print("donot merge single positions.")
    if debitexport is not None:
        debitexport["Betrag in EUR"] = debitexport["Betrag in EUR"].apply(lambda x: f"{x:.2f}".replace('.', ','))
    if transferexport is not None:
        transferexport["Betrag in EUR"] = transferexport["Betrag in EUR"].apply(lambda x: f"{x:.2f}".replace('.', ','))


    return debitexport,transferexport, doublesprocess

#    fullname = f"{personaldata['Name 1']} {personaldata['Name 2']}"
#personaldata =  masterdata.data.iloc[0]
# invoicedata = invoices.data['detailed'][invoices.data['detailed']['Empfänger Name'] == fullname]
#invoicetemplate = invoices.template_for_export

def find_soffice():
    """Locate the LibreOffice binary, or None.

    `soffice` is on PATH only on Linux (and on Windows/macOS only if someone
    put it there). Calling it bare meant the PDF fallback could not work on a
    Mac even with LibreOffice installed.
    """
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    candidates = [
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    return next((path for path in candidates if os.path.exists(path)), None)


def resolve_name_in_energydata(energydata, name):
    """Return the spelling of `name` used in the energy data columns, or None.

    EEG Faktura and the energy export disagree about trailing whitespace, so
    try the name as-is, with a trailing space, then with the last character
    dropped - the same three attempts the original code made inline.
    """
    for candidate in (name, name + " ", name[:-1]):
        try:
            energydata.loc[:, pd.IndexSlice[:, candidate, :, :]]
            return candidate
        except Exception:
            continue
    return None


def produce_invoices_and_save(energydata,invoicedata,masterdata,invoicetemplate,savedirfp,callback,
                              should_cancel=None):
    """Render and save one invoice per member.

    `callback(message, done, total)` drives the progress display.
    `should_cancel()` is polled once per member so the user can stop a long run.

    Returns a list of human-readable problems. The caller owns the worker
    lifecycle - this function no longer signals completion itself, because the
    old early `return None` skipped that signal and left the app hung.
    """
    _ensure_plotting()
    problems = []
    # fullname = f"{personaldata['Name 1']} {personaldata['Name 2']}"
    debit,transfer, doublesprocess = check_doubles(invoicedata)
    # debit, transfer = debit[cols_for_tbl], transfer[cols_for_tbl]
    energydata.index = pd.to_datetime(energydata.index, format="%d.%m.%Y %H:%M:%S")
    nr_all_persons = invoicedata["Empfänger Name"].unique().shape[0]
    for index,name in enumerate(invoicedata["Empfänger Name"].unique()):
    # for index, name in enumerate(["Gerhard Halder"]):
        if should_cancel is not None and should_cancel():
            problems.append(f"Abgebrochen nach {index} von {nr_all_persons} Rechnungen.")
            break
        print(f"({index+1}/{nr_all_persons}) Make invoice for {name}")
        callback(tr("({done}/{total}) Rechnung für {name}...",
                    done=index + 1, total=nr_all_persons, name=name), index, nr_all_persons)
        invoicethis = invoicedata[invoicedata["Empfänger Name"] == name]
        debits_this =  debit[debit["Empfänger Name"] == name]
        transfers_this = transfer[transfer["Empfänger Name"] == name]
        total_transfer_debit = "Rechnung"
        #if diff > 0 debit bigger than transfer -> Rechnung otherwise Gutschrift
        diff = debits_this["Pos. Bruttobetrag"].sum(axis = 0) -transfers_this["Pos. Bruttobetrag"].sum(axis = 0)
        if diff > 0:
            total_transfer_debit = "Rechnung"
            transfers_this.loc[:,['Pos. Nettobetrag','Pos. Bruttobetrag']]= -transfers_this.loc[:,['Pos. Nettobetrag','Pos. Bruttobetrag']]

        if diff < 0:
            total_transfer_debit = "Gutschrift"
            debits_this.loc[:,['Pos. Nettobetrag','Pos. Bruttobetrag']]= -debits_this.loc[:,['Pos. Nettobetrag','Pos. Bruttobetrag']]




        all_position_for_tbl = pd.concat([debits_this,transfers_this], axis = 0)
        postext =  all_position_for_tbl.copy()
        postext.loc[postext['Pos. Text'].str.contains('Mitgliedsgebuer'),'Pos. Text'] = ''
        all_position_for_tbl['Pos. Invoicetext'] = (all_position_for_tbl['Pos. Tarif'] + "\n"+ postext['Pos. Text'])
        all_position_for_tbl['Pos. Preis / Einheit'] = all_position_for_tbl['Pos. Preis / Einheit'].astype(float)

        all_position_for_tbl['Pos. Menge'] = all_position_for_tbl['Pos. Menge'].astype(str) + " " + all_position_for_tbl[ 'Pos. Mengeneinheit'].fillna("")
        all_position_for_tbl.loc[all_position_for_tbl['Pos. Preis / Einheit Euro/Cent'] == "Ct",'Pos. Preis / Einheit'] = all_position_for_tbl.loc[all_position_for_tbl['Pos. Preis / Einheit Euro/Cent'] == "Ct",'Pos. Preis / Einheit']/ 100
        sumnetto = str(round(all_position_for_tbl['Pos. Nettobetrag'].sum(),2))
        sumbrutto = str(round(all_position_for_tbl['Pos. Bruttobetrag'].sum(),2))



        cols_for_tbl = ['Pos. Invoicetext','Pos. Menge','Pos. Preis / Einheit','Pos. Nettobetrag','Pos. UST %','Pos. UST Betrag','Pos. Bruttobetrag']
        moneycols = ['Pos. Preis / Einheit','Pos. Nettobetrag','Pos. UST Betrag','Pos. Bruttobetrag']
        all_position_for_tbl[moneycols] = all_position_for_tbl[moneycols].map("{0:.2f}".format)
        all_position_for_tbl = all_position_for_tbl[cols_for_tbl]

        invoicequart = invoicethis["Abrechnung"].iloc[0]
        year,quart = invoicequart.split("-")[-2],invoicequart.split("-")[-1]

        parsing_dict = {}
        parsing_dict["EmpfängerName"] = invoicethis["Empfänger Name"].values[0]
        parsing_dict["EmpfängerAdresse1"] =invoicethis["Empfänger Adresse 1"].values[0]
        parsing_dict["EmpfängerAdresse2"] =invoicethis["Empfänger Adresse 2"].values[0]
        parsing_dict["invoiceitemstbl_contents"]= all_position_for_tbl.values.tolist()
        parsing_dict["Rechnung_Gutschrift"] = total_transfer_debit
        parsing_dict["community_name"] = masterdata.metadata['Bezeichnung']
        parsing_dict["community_street"] = masterdata.metadata['Straße']
        parsing_dict["community_streetnr"] = masterdata.metadata['StraßenNr.']
        parsing_dict["community_citycode"] = masterdata.metadata['PLZ']
        parsing_dict["community_city"] = masterdata.metadata['Wohnort']
        try:
            parsing_dict["community_phone"] = masterdata.metadata['TelefonNr.']
        except: pass
        parsing_dict["community_website"] = masterdata.metadata['Web Seite']
        parsing_dict["community_IBAN"] = masterdata.metadata['IBAN']
        parsing_dict["community_mail"] = masterdata.metadata['E-Mail']
        try:
            parsing_dict["community_companynumber"] = masterdata.metadata['Geschäftsnummer']
        except: pass
        invoicenumberstr = ""
        if total_transfer_debit == "Rechnung":
            invoicenumberstr = debits_this["Nummer"].iloc[0]
            parsing_dict["Überweisungstext"] = "Die gegenständliche Rechnungsforderung wird vereinbarungsgemäß von Ihrem Konto eingezogen."
        if total_transfer_debit == "Gutschrift":
            invoicenumberstr = transfers_this["Nummer"].iloc[0]
            parsing_dict["Überweisungstext"] = "Die gegenständliche Gutschrift wird vereinbarungsgemäß auf Ihr Konto überwiesen."

        parsing_dict["Rechnungsnummer"] = invoicenumberstr
        parsing_dict["DatumHeute"] = dt.datetime.today().strftime("%d.%m.%Y")
        parsing_dict["Jahr"] = year
        parsing_dict["Quartal"] = quart
        parsing_dict["TotalSumNetto"] = sumnetto
        parsing_dict["TotalSumBrutto"] = sumbrutto



        # print(parsing_dict)
        image_stream = BytesIO()
        sizemutiplier = 1.9

        fig, axs = plt.subplots(4, height_ratios=[0.3,10,10,10],figsize=(4.2 * sizemutiplier, 2.7 * sizemutiplier))
        #axs[0] is only for the spacing
        axs[0].set_xticklabels([])
        # prepare data for plot
        # check whether the energy direction is always the same
        name_new = resolve_name_in_energydata(energydata, name)
        if name_new is None:
            # Was `return None`, which abandoned the whole batch *and* skipped
            # the completion signal, hanging the app. Skip this member instead.
            msg = (f"{name}: kein passender Name in den Energiedaten gefunden - "
                   f"Rechnung übersprungen. Namen in Faktura und Energiedaten angleichen.")
            print(msg)
            problems.append(msg)
            plt.close(fig)
            continue

        name = name_new

        energydirections = energydata.xs(name, level="Name", axis=1).columns.get_level_values(level="Energy direction")
        meteringpointids = energydata.xs(name, level="Name", axis=1).columns.get_level_values(level="MeteringpointID")
        hatches = ['', '/', '\\', '|', '-', '+', 'x', 'o', 'O', '.', '*']
        edgecolors = ['none', 'black', 'green', 'red']
        hatches_this_person = [x for x, y in zip(hatches, range(0, meteringpointids.unique().shape[
            0]))]  # take nr meteringpoints hatches
        hatchnr = 0
        parsing_dict["TextfürVerbrauch"] = ""
        plotting_single = True

        def prepare_data_plotting_one_quantity(energy_through_evu, energy_through_eg,
                                               axs, plottext1, plottext2, hatch, edgecolor):
            print(f"Plotting with {plottext1} {plottext2}, {hatch}, {edgecolor}")
            energy_through_evu_weeklysum = energy_through_evu.groupby(
                energy_through_evu.index.strftime('%Y-%W')).sum()
            xaxis_energy_through_evu = []
            xaxis_energy_through_eeg = []
            for week, weektotalenergy in energy_through_evu.groupby(energy_through_evu.index.strftime('%Y-%W')):
                xaxis_energy_through_evu.append(
                    dt.datetime.strptime(f"{week}-1", "%Y-%U-%w"))  # the one saying we take the monday of the week
            energy_through_eeg_weeklysum = energy_through_eg.groupby(
                energy_through_eg.index.strftime('%Y-%W')).sum()
            for week, weekenergy_through_eg in energy_through_eg.groupby(energy_through_eg.index.strftime('%Y-%W')):
                xaxis_energy_through_eeg.append(dt.datetime.strptime(f"{week}-1", "%Y-%U-%w"))

            # throuw away the first and last week since they are only partly and will change the sum
            energy_through_evu_weeklysum = energy_through_evu_weeklysum.iloc[1:-1]
            energy_through_eeg_weeklysum = energy_through_eeg_weeklysum.iloc[1:-1]
            xaxis_energy_through_evu = xaxis_energy_through_evu[1:-1]
            # shift one day earlier

            xaxis_energy_through_eeg = xaxis_energy_through_eeg[1:-1]

            dailyhourmean_energy_through_evu = energy_through_evu.groupby(energy_through_evu.index.hour).mean()
            dailyhourmean_through_eeg = energy_through_eg.groupby(
                energy_through_eg.index.hour).mean()
            barwidth = dt.timedelta(days=3)
            xaxis_energy_through_evu = [x - 0.5 * barwidth for x in xaxis_energy_through_evu]
            xaxis_energy_through_eeg = [x + 0.5 * barwidth for x in xaxis_energy_through_eeg]

            energy_through_evu_weekday = energy_through_evu.groupby(
                energy_through_evu.index.strftime('%Y-%w')).sum()
            energy_through_evu_weekday = np.roll(energy_through_evu_weekday.values, shift=-1,
                                                 axis=0).T  # because it starts with sunday roll by one day
            energy_through_eg_weekday = energy_through_eg.groupby(energy_through_eg.index.strftime('%Y-%w')).sum()
            energy_through_eg_weekday = np.roll(energy_through_eg_weekday.values, shift=-1,
                                                axis=0).T  # because it starts with sunday roll by one day
            xaxis_weekdays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

            axs[1].bar(xaxis_energy_through_evu, energy_through_evu_weeklysum.values.flatten(), width=barwidth,
                       label=plottext1,
                       color="#69a4dc", hatch=hatch, edgecolor=edgecolor)
            # print(f"energy_through_evu_weeklysum:{energy_through_evu_weeklysum}")

            axs[1].bar(xaxis_energy_through_eeg, energy_through_eeg_weeklysum.values.flatten(), width=barwidth,
                       label=plottext2,
                       color="#f8ae42", hatch=hatch, edgecolor=edgecolor)
            # print(f"energy_through_evu_weeklysum:{energy_through_eeg_weeklysum}")
            axs[1].xaxis.set_major_locator(MonthLocator())
            axs[1].xaxis.set_major_formatter(DateFormatter('%b %Y'))
            # axs[1].xaxis.set_label_position("right")
            axs[1].set_ylabel("kWh")

            barwidth = 0.4
            axs[2].bar(dailyhourmean_energy_through_evu.index - 0.5 * barwidth,
                       dailyhourmean_energy_through_evu.values.flatten(), width=barwidth, color="#69a4dc", hatch=hatch,
                       edgecolor=edgecolor)
            axs[2].bar(dailyhourmean_through_eeg.index + 0.5 * barwidth, dailyhourmean_through_eeg.values.flatten(),
                       width=barwidth, color="#f8ae42", hatch=hatch, edgecolor=edgecolor)
            axs[2].set_xticks([0, 6, 12, 18, 24])
            axs[2].set_xticklabels(["0 Uhr", "6 Uhr", "12 Uhr", "18 Uhr", "24 Uhr"])
            axs[2].set_ylabel("kW")

            barwidth = 0.4
            axs[3].bar(np.linspace(0, 6, 7) - 0.5 * barwidth, energy_through_evu_weekday.flatten(), width=barwidth,
                       color="#69a4dc", tick_label=xaxis_weekdays, hatch=hatch, edgecolor=edgecolor)
            axs[3].bar(np.linspace(0, 6, 7) + 0.5 * barwidth, energy_through_eg_weekday.flatten(), width=barwidth,
                       color="#f8ae42", tick_label=xaxis_weekdays, hatch=hatch, edgecolor=edgecolor)
            axs[3].set_ylabel("kWh")
            axs[1].legend(fontsize='small', loc=1, bbox_to_anchor=(0.8, 1.22))
        sidetext = ""

        def read_series(energydirection, meteringpointid):
            """Read one energy series for this member.

            `meteringpointid=None` aggregates across all of their metering
            points. Returns a dict, or None when the data is not there.

            Returning None matters: the previous version caught the failure and
            fell through to the plotting call with `energy_through_evu`,
            `plottext1` etc. still bound from the *previous* metering point or
            the *previous member*, so a failed lookup silently drew somebody
            else's energy data onto this member's invoice.
            """
            mp = slice(None) if meteringpointid is None else meteringpointid
            aggregated = meteringpointid is None
            zp = "" if aggregated else f" ZP {meteringpointid[-6:]}"
            try:
                if energydirection == "GENERATION":
                    total = energydata.loc[:, pd.IndexSlice[mp, name, energydirection,
                        "Gesamte gemeinschaftliche Erzeugung [KWH]"]].sort_index()
                    through_evu = energydata.loc[:, pd.IndexSlice[mp, name, energydirection,
                        "Gesamt/Überschusserzeugung, Gemeinschaftsüberschuss [KWH]"]].sort_index()
                    if aggregated:
                        total, through_evu = total.sum(axis=1), through_evu.sum(axis=1)
                    through_eg = pd.DataFrame(
                        np.nan_to_num(total.values, nan=0.0) - np.nan_to_num(through_evu.values, nan=0.0),
                        index=total.index)
                    text1 = f"Energielieferung an außerhalb der Energiegemeinschaft{' von' + zp if zp else ''}"
                    text2 = f"Energielieferung über unsere Energiegemeinschaft{' von' + zp if zp else ''}"
                else:
                    total = energydata.loc[:, pd.IndexSlice[mp, name, energydirection,
                        "Gesamtverbrauch lt. Messung (bei Teilnahme gem. Erzeugung) [KWH]"]].sort_index()
                    through_eg = energydata.loc[:, pd.IndexSlice[mp, name, energydirection,
                        "Eigendeckung gemeinschaftliche Erzeugung [KWH]"]].sort_index()
                    if aggregated:
                        total, through_eg = total.sum(axis=1), through_eg.sum(axis=1)
                    through_evu = pd.DataFrame(
                        np.nan_to_num(total.values, nan=0.0) - np.nan_to_num(through_eg.values, nan=0.0),
                        index=total.index)
                    text1 = f"Energiebezug von Stromlieferant{' für' + zp if zp else ''}"
                    text2 = f"Energiebezug über unsere Energiegemeinschaft{' für' + zp if zp else ''}"
            except Exception as e:
                print(f"No energy data for {name} / {energydirection} / {meteringpointid}: {e}")
                return None

            total_eg = float(np.nansum(through_eg.values))
            grand_total = float(np.nansum(total.values))
            # A member with no readings would otherwise divide by zero here and
            # lose the whole chart to the bare except.
            share = (total_eg / grand_total * 100) if grand_total else 0.0
            return {"evu": through_evu, "eg": through_eg,
                    "text1": text1, "text2": text2,
                    "total_eg": total_eg, "share": share}

        def compose_sidetext(energydirection, meteringpointid, single, total_eg, share):
            zp = "" if meteringpointid is None else f"ZP {meteringpointid[-6:]}"
            if energydirection == "GENERATION":
                if single or not zp:
                    return (f"Insgesamt wurden {total_eg:.1f}kWh an die Energiegemeinschaft verkauft. \n"
                            f"Dies ist {share:.1f}% deiner gesamten erzeugten Energie in diesem Quartal.\n")
                return (f"Von {zp} wurden {total_eg:.1f}kWh an die Energiegemeinschaft geliefert. \n"
                        f"Dies ist {share:.1f}% der erzeugten Energie in diesem Quartal.\n")
            if single or not zp:
                return (f"Insgesamt wurden {total_eg:.1f}kWh über die Energiegemeinschaft bezogen. \n"
                        f"Dies ist {share:.1f}% deines Gesamtenergieverbrauchs in diesem Quartal.\n")
            return (f"Von {zp} wurden {total_eg:.1f}kWh über die Energiegemeinschaft bezogen. \n"
                    f"Dies ist {share:.1f}% des Verbrauchs in diesem Quartal.\n")

        unique_meteringpoints = meteringpointids.unique()
        single_meteringpoint = unique_meteringpoints.shape[0] == 1
        for energydirection in energydirections.unique():
            # More than four metering points: one aggregated plot instead of
            # one per point, otherwise the chart is unreadable.
            if len(unique_meteringpoints) > 4:
                targets = [None]
            else:
                targets = list(unique_meteringpoints)

            for meteringpointid in targets:
                series = read_series(energydirection, meteringpointid)
                if series is None:
                    where = "alle Zählpunkte" if meteringpointid is None else meteringpointid
                    problems.append(f"{name}: keine Energiedaten für {energydirection} / {where} - "
                                    f"dieser Teil fehlt in der Grafik")
                    continue
                # Vary the hatch first and only advance the edge colour once
                # the hatches wrap, so the pair stays unique for 11 x 4 series.
                # Taking both modulo hatchnr made series 5 identical to series 1.
                hatch = hatches[hatchnr % len(hatches)]
                edgecolor = edgecolors[(hatchnr // len(hatches)) % len(edgecolors)]
                sidetext += compose_sidetext(energydirection, meteringpointid,
                                             single_meteringpoint,
                                             series["total_eg"], series["share"])
                parsing_dict["TextfürVerbrauch"] = sidetext
                prepare_data_plotting_one_quantity(series["evu"], series["eg"],
                                                   axs, series["text1"], series["text2"],
                                                   hatch, edgecolor)
                hatchnr += 1

        invoicetemplate.render(parsing_dict)
        # fig.set_size(3.49, 1.97)
        # fig.tight_layout(rect=(0.05, 0.1, 1, 0.8))
        fig.subplots_adjust(wspace=0.4, hspace=0.3)
        plt.savefig(image_stream, format="png")
        # plt.show()

        plt.close()
        image_stream.seek(0)

        invoicetemplate.replace_pic("Image2", image_stream)



        #save
        namefile = f"Rechnung_{year}_q{quart}_{invoicethis["Empfänger Vorame"].iloc[0]}_{invoicethis["Empfänger Nachname"].iloc[0]}"
        savepathdocx = os.path.join(savedirfp, f"{namefile}.docx")
        print(f"Save invoice of {name} to {savepathdocx}")
        invoicetemplate.save(savepathdocx)

        def generate_pdf(doc_path, path):
            """Convert one .docx to .pdf. Returns the pdf path, or None on failure.

            Runs on a worker thread, so it must not touch Qt widgets - failures
            are returned to the caller and reported once at the end.
            """
            pdf_path = doc_path.rsplit(".", 1)[0] + ".pdf"
            try:
                from docx2pdf import convert     # imported here, not at startup
                convert(doc_path, pdf_path)
            except Exception as word_error:
                print(f"Word conversion failed ({word_error}), trying LibreOffice")
                soffice = find_soffice()
                if soffice is None:
                    print("No LibreOffice found either - install Word or LibreOffice "
                          "to get PDFs instead of .docx")
                    return None
                try:
                    subprocess.call([soffice,
                                     '--headless',
                                     '--convert-to',
                                     'pdf',
                                     '--outdir',
                                     path,
                                     doc_path])
                except Exception as soffice_error:
                    print(f"LibreOffice conversion failed too: {soffice_error}")
                    return None
            return pdf_path if os.path.exists(pdf_path) else None

        print(f"Save invoice of {name} to {savedirfp}")

        if generate_pdf(savepathdocx, savedirfp) is None:
            problems.append(f"{name}: PDF-Erzeugung fehlgeschlagen - nur die .docx wurde gespeichert. "
                            f"Ist Word oder LibreOffice installiert?")

    return problems

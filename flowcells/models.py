import functools
import re
import uuid as uuid_object

from django.contrib.postgres.fields import ArrayField, JSONField
from django.core.urlresolvers import reverse
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
import pagerange
from projectroles.models import Project
from filesfolders.models import File, Folder

from digestiflow.users.models import User
from barcodes.models import BarcodeSet, BarcodeSetEntry
from sequencers.models import SequencingMachine


def pretty_range(value):
    return pagerange.PageRange(value).range


#: Status for "initial"/"not started", not automatically started yet for conversion.
STATUS_INITIAL = "initial"

#: Status for "ready to start"
STATUS_READY = "ready"

#: Status for "in progress"
STATUS_IN_PROGRESS = "in_progress"

#: Status for "complete" (automatic)
STATUS_COMPLETE = "complete"

#: Status for "complete_warnings" (manual)
STATUS_COMPLETE_WARNINGS = "complete_warnings"

#: Status for "failed" (automatic)
STATUS_FAILED = "failed"

#: Status for closed/released/receival confirmed (by user)
STATUS_CLOSED = "closed"

#: Status for confirmed failed/confirmed canceled (by user)
STATUS_CANCELED = "canceled"

#: Status for "skipped" (only used for conversion)
STATUS_SKIPPED = "skipped"

#: Statuses for sequencing
SEQUENCING_STATUS_CHOICES = (
    (STATUS_INITIAL, "not started"),
    (STATUS_IN_PROGRESS, "in progress"),
    (STATUS_COMPLETE, "complete"),
    (STATUS_COMPLETE_WARNINGS, "complete with warnings"),
    (STATUS_CLOSED, "released"),
    (STATUS_FAILED, "failed"),
    (STATUS_CANCELED, "failured confirmed"),
)

#: Statuses for base call to sequence conversion
CONVERSION_STATUS_CHOICES = (
    (STATUS_INITIAL, "keep unstarted"),
    (STATUS_READY, "ready to start"),
    (STATUS_IN_PROGRESS, "in progress"),
    (STATUS_COMPLETE, "complete"),
    (STATUS_COMPLETE_WARNINGS, "complete with warnings"),
    (STATUS_FAILED, "failed"),
    (STATUS_CLOSED, "released"),
    (STATUS_CANCELED, "failured confirmed"),
    (STATUS_SKIPPED, "skipped"),
)

#: Statuses for delivery
DELIVERY_STATUS_CHOICES = (
    (STATUS_INITIAL, "not started"),
    (STATUS_IN_PROGRESS, "in progress"),
    (STATUS_COMPLETE, "complete"),
    (STATUS_COMPLETE_WARNINGS, "complete with warnings"),
    (STATUS_CLOSED, "received"),
    (STATUS_FAILED, "canceled"),
    (STATUS_CANCELED, "canceled confirmed"),
    (STATUS_SKIPPED, "skipped"),
)

#: Delivery of sequences (FASTQ)
DELIVERY_TYPE_SEQ = "seq"

#: Delivery of base calls (BCL)
DELIVERY_TYPE_BCL = "bcl"

#: Delivery of both sequences and base calls
DELIVERY_TYPE_BOTH = "seq_bcl"

#: Delivery options
DELIVERY_CHOICES = (
    (DELIVERY_TYPE_SEQ, "sequences"),
    (DELIVERY_TYPE_BCL, "base calls"),
    (DELIVERY_TYPE_BOTH, "sequences + base calls"),
)


#: RTA version key for v1
RTA_VERSION_V1 = 1

#: RTA version key for v2
RTA_VERSION_V2 = 2

#: RTA version key for 'other'
RTA_VERSION_OTHER = 0

#: RTA version used for a flow cell
RTA_VERSION_CHOICES = (
    #: RTA v1.x, old bcl2fastq required
    (RTA_VERSION_V1, "RTA v1"),
    #: RTA v2.x, bcl2fast2 required
    (RTA_VERSION_V2, "RTA v2"),
    #: other, for future-proofness
    (RTA_VERSION_OTHER, "other"),
)


class FlowCellManager(models.Manager):
    """Manager for custom table-level SequencingMachine queries"""

    # TODO: properly test searching..

    def find(self, search_term, _keywords=None):
        """Return objects or links matching the query.

        :param search_term: Search term (string)
        :param keywords: Optional search keywords as key/value pairs (dict)
        :return: Python list of BaseFilesfolderClass objects
        """
        objects = super().get_queryset()
        objects = objects.filter(
            Q(vendor_id__icontains=search_term)
            | Q(label__icontains=search_term)
            | Q(manual_label__icontains=search_term)
        )
        return objects


class FlowCell(models.Model):
    """Information stored for each flow cell"""

    #: DateTime of creation
    date_created = models.DateTimeField(auto_now_add=True, help_text="DateTime of creation")

    #: DateTime of last modification
    date_modified = models.DateTimeField(auto_now=True, help_text="DateTime of last modification")

    #: UUID used for identification throughout SODAR.
    sodar_uuid = models.UUIDField(
        default=uuid_object.uuid4, unique=True, help_text="Barcodeset SODAR UUID"
    )

    #: The project containing this barcode set.
    project = models.ForeignKey(Project, help_text="Project in which this flow cell belongs")

    #: Run date of the flow cell
    run_date = models.DateField()

    #: The sequencer used for processing this flow cell
    sequencing_machine = models.ForeignKey(SequencingMachine, null=False, on_delete=models.PROTECT)

    #: The run number on the machine
    run_number = models.PositiveIntegerField()

    #: The slot of the machine
    slot = models.CharField(max_length=1)

    #: The vendor ID of the flow cell name
    vendor_id = models.CharField(max_length=40)

    #: The label of the flow cell
    label = models.CharField(blank=True, null=True, max_length=100)

    #: Manual override for the flow cell label.
    manual_label = models.CharField(
        blank=True,
        null=True,
        max_length=100,
        help_text="Manual label for overriding the one from the folder name",
    )

    #: Short description length
    description = models.TextField(
        blank=True, null=True, help_text="Short description of the flow cell"
    )

    #: Number of lanes on the flow cell
    num_lanes = models.IntegerField(
        blank=False,
        null=False,
        default=8,
        help_text="Number of lanes on flowcell 8 for HiSeq, 4 for NextSeq",
    )

    #: Name of the sequencing machine operator
    operator = models.CharField(
        blank=True, null=True, max_length=100, verbose_name="Sequencer Operator"
    )

    #: The user responsible for demultiplexing
    demux_operator = models.ForeignKey(
        User,
        blank=True,
        null=True,
        verbose_name="Demultiplexing Operator",
        related_name="demuxed_flowcells",
        on_delete=models.SET_NULL,
        help_text="User responsible for demultiplexing",
    )

    #: RTA version used, required for picking BCL to FASTQ and demultiplexing software
    rta_version = models.IntegerField(
        blank=False,
        null=False,
        default=RTA_VERSION_V2,
        choices=RTA_VERSION_CHOICES,
        help_text="Major RTA version, implies bcl2fastq version",
    )

    #: Status of sequencing
    status_sequencing = models.CharField(
        blank=False,
        null=False,
        max_length=50,
        default=STATUS_INITIAL,
        choices=SEQUENCING_STATUS_CHOICES,
        help_text="Choices for sequencing",
    )

    #: Status of base call to sequence conversion
    status_conversion = models.CharField(
        blank=False,
        null=False,
        max_length=50,
        default=STATUS_INITIAL,
        choices=CONVERSION_STATUS_CHOICES,
        help_text="Choices for sequencing",
    )

    #: Status of data delivery
    status_delivery = models.CharField(
        blank=False,
        null=False,
        max_length=50,
        default=STATUS_INITIAL,
        choices=DELIVERY_STATUS_CHOICES,
        help_text="Choices for sequencing",
    )

    #: What to deliver: sequences, base calls, or both.
    delivery_type = models.CharField(
        blank=False,
        null=False,
        max_length=50,
        default=DELIVERY_TYPE_SEQ,
        choices=DELIVERY_CHOICES,
        help_text="Choices for data delivery type",
    )

    #: Information about the planned read in Picard notation, that is B for Sample Barcode, M for molecular barcode,
    #: T for Template, and S for skip.
    planned_reads = models.CharField(
        max_length=200, blank=True, null=True, help_text="Specification of the planned reads"
    )

    #: Information about the currently performed reads in Picard notation.
    current_reads = models.CharField(
        max_length=200, blank=True, null=True, help_text="Specification of the current reads"
    )

    #: Number of mismatches to allow, defaults to ``None`` which triggers to use the default.
    barcode_mismatches = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Number of mismatches to allow"
    )

    #: Search-enabled manager.
    objects = FlowCellManager()

    def get_sent_messages(self):
        """Return all published messages that are no drafts."""
        return self.messages.filter(state=MSG_STATE_SENT)

    @property
    def name(self):
        """Used for sorting results."""
        return self.vendor_id

    def get_absolute_url(self):
        return reverse(
            "flowcells:flowcell-detail",
            kwargs={"project": self.project.sodar_uuid, "flowcell": self.sodar_uuid},
        )

    def get_full_name(self):
        """Return full flow cell name"""
        values = (
            self.run_date,
            self.sequencing_machine,
            self.run_number,
            self.slot,
            self.vendor_id,
            self.label,
        )
        if all(not x for x in values):
            return ""
        else:
            run_date = "" if not self.run_date else self.run_date.strftime("%y%m%d")
            vendor_id = "" if not self.sequencing_machine else self.sequencing_machine.vendor_id
            run_number = "{:04}".format(0 if not self.run_number else self.run_number)
            return "_".join(
                map(str, (run_date, vendor_id, run_number, self.slot, self.vendor_id, self.label))
            )

    @functools.lru_cache()
    def get_index_errors(self):
        """Analyze index histograms for problems and inconsistencies with sample sheet.

        Return map from lane number, index read, and sequence to list of errors.
        """
        result = {}
        for hist in self.index_histograms.all():
            # Collect sequences we expect to see for this lane and read number
            expected_seqs = set()
            for library in self.libraries.filter(lane_numbers__contains=[hist.lane]):
                if hist.index_read_no == 0:
                    barcode = library.barcode
                    barcode_seq = library.barcode_seq
                else:
                    barcode = library.barcode2
                    barcode_seq = library.barcode_seq2
                    # TODO: revcomp in case of sequencing workflow B
                if barcode:
                    expected_seqs.add(barcode.sequence)
                elif barcode_seq:
                    expected_seqs.add(barcode_seq)
            # Collect errors and write into result
            for seq, _ in hist.histogram.items():
                errors = []
                if all(s == "N" for s in seq):
                    continue  # skip all-Ns
                if seq not in expected_seqs:
                    errors += [
                        "found barcode {} on lane {} and index read {} in BCLs but not in sample sheet".format(
                            seq, hist.lane, hist.index_read_no
                        )
                    ]
                if errors:
                    result[(hist.lane, hist.index_read_no, seq)] = errors
        return result

    @functools.lru_cache()
    def get_sample_sheet_errors(self):
        """Analyze the sample sheet for problems and inconsistencies.

        Returns map from library UUID to dict with field names to list of error messages.
        """
        # Resulting error map, empty if no errors
        result = {}
        # Library from UUID
        by_uuid = {}
        # Maps for ambiguity checking
        by_name = {}  # (lane, name) => library
        by_barcode = {}  # (lane, barcode) => library
        by_barcode2 = {}  # (lane, barcode) => library

        # Gather information about libraries, directly validate names and lane numbers
        for library in self.libraries.all():
            by_uuid[library.sodar_uuid] = library
            # Directly check for invalid characters
            if not re.match("^[a-zA-Z0-9_-]+$", library.name):
                result.setdefault(library.sodar_uuid, {}).setdefault("name", []).append(
                    "Library names may only contain alphanumeric characters, hyphens, and underscores"
                )
            # Directly check for invalid lanes
            bad_lanes = list(
                sorted(no for no in library.lane_numbers if no < 1 or no > self.num_lanes)
            )
            if bad_lanes:
                result.setdefault(library.sodar_uuid, {}).setdefault(
                    "lane",
                    [
                        "Flow cell does not have lane{} #{}".format(
                            "s" if len(bad_lanes) > 1 else "", pretty_range(bad_lanes)
                        )
                    ],
                )
            # Store per-lane information for ambiguity evaluation
            for lane in library.lane_numbers:
                by_name.setdefault((lane, library.name), []).append(library)
                by_barcode.setdefault((lane, library.get_barcode_seq()), {})[
                    library.sodar_uuid
                ] = library
                by_barcode2.setdefault((lane, library.get_barcode_seq2()), {})[
                    library.sodar_uuid
                ] = library

        # Check uniqueness of sample name with lane.
        bad_lanes = {}
        for (lane, name), libraries in by_name.items():
            if len(libraries) != 1:
                for library in libraries:
                    bad_lanes.setdefault(library.sodar_uuid, []).append(lane)
        for sodar_uuid, lanes in bad_lanes.items():
            library = by_uuid[sodar_uuid]
            result.setdefault(sodar_uuid, {}).setdefault("name", []).append(
                "Library name {} is not unique for lane{} {}".format(
                    library.name, "s" if len(lanes) > 1 else "", pretty_range(lanes)
                )
            )

        # Check uniqueness of barcode sequence combination with lane.  This is a bit more involved as a clash in
        # one of the indices is not yet an error, it has to be in both.
        bad_lanes = {}
        for (lane, seq), libraries in by_barcode.items():
            for library in libraries.values():
                other_libraries = by_barcode2[(lane, library.get_barcode_seq2())]
                clashes = (set(libraries.keys()) & set(other_libraries.keys())) - set(
                    [library.sodar_uuid]
                )
                if clashes:
                    bad_lanes.setdefault(library.sodar_uuid, []).append(lane)
        for sodar_uuid, lanes in bad_lanes.items():
            library = by_uuid[sodar_uuid]
            keys = []
            if not library.get_barcode_seq() and not library.get_barcode_seq2():
                keys = ["barcode", "barcode2"]
            else:
                if library.get_barcode_seq():
                    keys.append("barcode")
                if library.get_barcode_seq2():
                    keys.append("barcode2")
            for key in keys:
                result.setdefault(sodar_uuid, {}).setdefault(key, []).append(
                    "Barcode combination {}/{} is not unique for lane{} {}".format(
                        library.get_barcode_seq() or "-",
                        library.get_barcode_seq2() or "-",
                        "s" if len(lanes) > 1 else "",
                        pretty_range(lanes),
                    )
                )
        return result

    def __str__(self):
        return "FlowCell %s" % self.get_full_name()

    class Meta:
        unique_together = ("vendor_id", "run_number", "sequencing_machine")
        ordering = ("-run_date", "sequencing_machine", "run_number", "slot")


#: Reference used for identifying human samples
REFERENCE_HUMAN = "hg19"

#: Reference used for identifying mouse samples
REFERENCE_MOUSE = "mm9"

#: Reference used for identifying fly samples
REFERENCE_FLY = "dm6"

#: Reference used for identifying fish samples
REFERENCE_FISH = "danRer6"

#: Reference used for identifying rat samples
REFERENCE_RAT = "rn11"

#: Reference used for identifying worm samples
REFERENCE_WORM = "ce11"

#: Reference used for identifying yeast samples
REFERENCE_YEAST = "sacCer3"

#: Reference used for identifying other samples
REFERENCE_OTHER = "__other__"

#: Reference sequence choices, to identify organisms
REFERENCE_CHOICES = (
    #: H. sapiens
    (REFERENCE_HUMAN, "human"),
    #: M. musculus
    (REFERENCE_MOUSE, "mouse"),
    #: D. melanogaster
    (REFERENCE_FLY, "fly"),
    #: D. rerio
    (REFERENCE_FISH, "zebrafish"),
    #: R. norvegicus
    (REFERENCE_RAT, "rat"),
    #: C. elegans
    (REFERENCE_WORM, "worm"),
    #: S. cerevisae
    (REFERENCE_YEAST, "yeast"),
    #: other
    (REFERENCE_OTHER, "other"),
)


class LibraryManager(models.Manager):
    """Manager for custom table-level Library queries"""

    # TODO: properly test searching..

    def find(self, search_term, _keywords=None):
        """Return objects or links matching the query.

        :param search_term: Search term (string)
        :param keywords: Optional search keywords as key/value pairs (dict)
        :return: Python list of BaseFilesfolderClass objects
        """
        objects = super().get_queryset()
        objects = objects.filter(
            Q(name=search_term)
            | Q(barcode__sequence=search_term)
            | Q(barcode_seq=search_term)
            | Q(barcode2__sequence=search_term)
            | Q(barcode_seq2=search_term)
        )
        return objects


class Library(models.Model):
    """The data stored for each library that is to be sequenced
    """

    #: DateTime of creation
    date_created = models.DateTimeField(auto_now_add=True, help_text="DateTime of creation")

    #: DateTime of last modification
    date_modified = models.DateTimeField(auto_now=True, help_text="DateTime of last modification")

    #: UUID used for identification throughout SODAR.
    sodar_uuid = models.UUIDField(
        default=uuid_object.uuid4, unique=True, help_text="Object SODAR UUID"
    )

    #: The flow cell that this library has been sequenced on
    flow_cell = models.ForeignKey(FlowCell, related_name="libraries", on_delete=models.CASCADE)

    #: The name of the library
    name = models.CharField(max_length=100)

    #: The organism to assume for this library, used for QC
    reference = models.CharField(
        null=True, blank=True, max_length=100, default="hg19", choices=REFERENCE_CHOICES
    )

    #: The barcode used for first barcode index this library
    barcode = models.ForeignKey(BarcodeSetEntry, null=True, blank=True, on_delete=models.PROTECT)

    #: Optional a sequence entered directly for the first barcode
    barcode_seq = models.CharField(max_length=200, null=True, blank=True)

    #: The barcode used for second barcode index this library
    barcode2 = models.ForeignKey(
        BarcodeSetEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="barcodes2"
    )

    #: Optionally, a sequence entered directly for the second barcode.  Entered as for dual indexing workflow A.
    barcode_seq2 = models.CharField(max_length=200, null=True, blank=True)

    #: The lanes that the library was sequenced on on the flow cell
    lane_numbers = ArrayField(models.IntegerField(validators=[MinValueValidator(1)]))

    #: Search-enabled manager.
    objects = LibraryManager()

    class Meta:
        ordering = ["name"]

    def get_barcode_seq(self):
        """Return barcode sequence #1 either from barcode or bacode_seq"""
        if self.barcode:
            return self.barcode.sequence
        else:
            return self.barcode_seq

    def get_barcode_seq2(self):
        """Return barcode sequence #2 either from barcode or bacode_seq"""
        if self.barcode2:
            return self.barcode2.sequence
        else:
            return self.barcode_seq2

    def get_absolute_url(self):
        return self.flow_cell.get_absolute_url()

    def __str__(self):
        return "Library {} on lane(s) {} for {}".format(
            self.name, self.lane_numbers, self.flow_cell
        )


class LaneIndexHistogram(models.Model):
    """Information about the index sequence distribution on a lane for a FlowCell"""

    #: DateTime of creation
    date_created = models.DateTimeField(auto_now_add=True, help_text="DateTime of creation")

    #: DateTime of last modification
    date_modified = models.DateTimeField(auto_now=True, help_text="DateTime of last modification")

    #: UUID used for identification throughout SODAR.
    sodar_uuid = models.UUIDField(
        default=uuid_object.uuid4, unique=True, help_text="Object SODAR UUID"
    )

    #: The flow cell this information is for.
    flowcell = models.ForeignKey(
        FlowCell, null=False, on_delete=models.CASCADE, related_name="index_histograms"
    )

    #: The lane that this is for.
    lane = models.PositiveIntegerField(null=False, help_text="The lane this information is for.")

    #: The number of the index read that this information is for.
    index_read_no = models.PositiveIntegerField(
        null=False, help_text="The index read this information is for."
    )

    #: The sample size used.
    sample_size = models.PositiveIntegerField(null=False, help_text="Number of index reads read")

    #: The histogram information as a dict from sequence to count.
    histogram = JSONField(help_text="The index histogram information")

    def __str__(self):
        return "Index Histogram index {} lane {} flowcell {}".format(
            self.index_read_no, self.lane, self.flowcell.get_full_name()
        )

    class Meta:
        unique_together = ("flowcell", "lane", "index_read_no")
        ordering = ("flowcell", "lane", "index_read_no")


#: Message state for draft
MSG_STATE_DRAFT = "draft"

#: Message state for sent
MSG_STATE_SENT = "sent"

#: Choices for message states
MSG_STATE_CHOICES = ((MSG_STATE_DRAFT, "Draft"), (MSG_STATE_SENT, "Sent"))

#: Format is plain text.
FORMAT_PLAIN = "text/plain"

#: Format is Markdown.
FORMAT_MARKDOWN = "text/markdown"

#: Choices for the format
FORMAT_CHOICES = ((FORMAT_PLAIN, "Plain Text"), (FORMAT_MARKDOWN, "Markdown"))


class Message(models.Model):
    """A message that is attached to a FlowCell."""

    #: DateTime of creation
    date_created = models.DateTimeField(auto_now_add=True, help_text="DateTime of creation")

    #: DateTime of last modification
    date_modified = models.DateTimeField(auto_now=True, help_text="DateTime of last modification")

    #: UUID used for identification throughout SODAR.
    sodar_uuid = models.UUIDField(
        default=uuid_object.uuid4, unique=True, help_text="Object SODAR UUID"
    )

    #: The flow cell that this library has been sequenced on
    author = models.ForeignKey(User, related_name="messages", null=True, on_delete=models.SET_NULL)

    #: The flow cell that this library has been sequenced on
    flow_cell = models.ForeignKey(FlowCell, related_name="messages", on_delete=models.CASCADE)

    #: The state of the message.
    state = models.CharField(
        max_length=50,
        null=False,
        choices=MSG_STATE_CHOICES,
        default=MSG_STATE_DRAFT,
        help_text="Status of the message",
    )

    #: The format of the body.
    body_format = models.CharField(
        max_length=50,
        null=False,
        choices=FORMAT_CHOICES,
        default=FORMAT_PLAIN,
        help_text="Format of the message body",
    )

    #: A list of tags.
    tags = ArrayField(models.CharField(max_length=100, blank=False), blank=True, default=list)

    #: The title of the message
    subject = models.CharField(max_length=200, null=True, blank=True, help_text="Message subject")

    #: Body text.
    body = models.TextField(null=False, blank=False, help_text="Message body")

    #: Folder for the attachments, if any.
    attachment_folder = models.ForeignKey(
        Folder, null=True, blank=True, help_text="Folder for the attachments, if any.",
        on_delete=models.PROTECT
    )

    def delete(self,*args, **kwargs):
        result = super().delete(*args, **kwargs)
        if self.attachment_folder:
            self.attachment_folder.delete()
        return result

    class Meta:
        ordering = ("date_created",)

    def get_absolute_url(self):
        if self.state == MSG_STATE_DRAFT:
            suffix = "#message-form"
        else:
            suffix = "#message-%s" % self.sodar_uuid
        return (
            reverse(
                "flowcells:flowcell-detail",
                kwargs={
                    "project": self.flow_cell.project.sodar_uuid,
                    "flowcell": self.flow_cell.sodar_uuid,
                },
            )
            + suffix
        )

    def get_attachment_files(self):
        """Returns QuerySet with the attached files"""
        if not self.attachment_folder:
            return Folder.objects.none()
        else:
            return self.attachment_folder.filesfolders_file_children.all()


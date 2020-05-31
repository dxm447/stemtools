import os
import struct
import numpy as np
import h5py
from collections import OrderedDict
from __future__ import print_function, division, absolute_import

class Frms6Reader(object):
    """ This class allows to access frm6 files
    """

    # For more information on struct format string see
    # https://docs.python.org/3/library/struct.html

    fileHeaderFormat = (
        '=' +  # first character indicates byte order. Here: native
        'H' +  # unsigned short myLength: Number of bytes in file header
        'H' +  # unsigned short fhLength: Number of bytes in frame header
        'B' +  # unsigned char nCCDs: Number of CCD to be read out (???)
        'B' +  # unsigned char width: Number of channels
        'B' +  # unsigned char maxHeight (maximum) Number of lines
        'B' +  # unsigned char version Format version
        '80s' +  # char dataSetID[80]: filename
        'H' +  # unsigned short the_width The true number of channels
        'H' +  # unsigned short the_maxHeight the true (maximum) number of
               # lines
        '932x'  # char fill[932] reserves space
    )
    fileHeaderSizeInBytes = struct.calcsize(fileHeaderFormat)
    fileHeaderStruct = struct.Struct(fileHeaderFormat)

    # Note:  unsigned <variable name> usually defines unsigned int
    # src: https://stackoverflow.com/questions/1171839/what-is-the-unsigned-datatype
    frameHeaderFormat = (
        '=' +  # first character indicates byte order. Here: native
        'B' +  # signed char start: starting line, indicates window mode if not
        'B' +  # unsigned char info: info byte
        'B' +  # unsigned char id: CCD id
        'B' +  # unsigned char height: number of lines in following frame
        'I' +  # unsigned int tv_sec: start data taking time in seconds
        'I' +  # unsigned int tv_usec: start data taking time in microseconds
        'I' +  # unsigned int index: index number
        'd' +  # double	temp: temperature voltage
        'H' +  # unsigned short the_start: true starting line, indicates
               #  window mode if > 0
        'H' +  # unsigned short the_height: the true number of lines in
               # following frame
        'I' +  # unsigned int external_id: Frame ID from an external trigger,
               # e.g. the bunch ID at DESY/FLASH
        # Here starts the union BunchID_t
        'Q' +  # uint64_t id. Should be as large as unsigned long long
        # Here starts another struct d
        # 'I' +  # unsigned (?) status
        # 'I' +  # unsigned (?) fiducials
        # 'I' +  # unsigned (?) wf: wrap flag (?)
        # 'I' +  # unsigned (?) seconds
        # Struct d ends here
        # Here starts another struct detailS, new for SACLA
        # 'I' +  # unsigned (?) status
        # 'I' +  # unsigned (?) info
        # 'I' +  # unsigned (?) wf: wrap flag (?)
        # 'I' +  # unsigned (?) fiducials: bunch id (?)
        # Struct detailS ends here
        # '8B' +  # unsigned char raw[8]: byte-wise access
        # Union BunchID_t ends here
        '24x'  # char fill[24] reserves space
    )
    frameHeaderSizeInBytes = struct.calcsize(frameHeaderFormat)
    frameHeaderStruct = struct.Struct(frameHeaderFormat)

    def __init__(self):
        pass
    
    @staticmethod
    def getFrameSizeInBytes(frameWidth, frameHeight):
        """ Convenience method to determine the frame size (without frame
        header!)

        Args:
            frameWidth (int): width of the frame
            frameHeight (int): height of the frame

        Returns:
            int: Frame size in bytes

        """
        return struct.calcsize(
            str(frameWidth * frameHeight) + 'h'
        )
    
    @classmethod
    def getFrameHeaders(cls, fn):
        """ Reads the frame headers of an entire frms6 file. The frame header
        keys are:

            * start
            * info
            * id
            * height
            * tv_sec
            * tv_usec
            * index
            * temp
            * maxHeight

        Args:
            fn (str): fully qualified file name

        Returns:
            dict: Contents of the all frame headers subdivided into lists, with
                one list per frame header key
        """

        frameHeight, frameWidth, numberOfFrames = Frms6Reader.getDataShape(fn)

        # We already know the format of the file header and the frame
        # header (see above), but we have yet to declare the format of the
        # frames. h -> short
        frameSizeInBytes = cls.getFrameSizeInBytes(frameWidth, frameHeight)

        # Remember contents of the frame header:
        # frame_dict = OrderedDict([
        #     ("start", frame_header_item[0]),
        #     ("info", frame_header_item[1]),
        #     ("id", frame_header_item[2]),
        #     ("height", frame_header_item[3]),
        #     ("tv_sec", frame_header_item[4]),
        #     ("tv_usec", frame_header_item[5]),
        #     ("index", frame_header_item[6]),
        #     ("temp", frame_header_item[7]),
        #     ("maxHeight", frame_header_item[8])
        # ])
        # Each items gets its own list:
        frameStart = []
        frameInfo = []
        frameId = []
        frameHeight = []
        frameTvSec = []
        frameTvUsec = []
        frameIndex = []
        frameTemp = []
        frameMaxHeight = []

        with open(fn, 'rb') as fh:
            # When reading the file, we'll jump directly to the frame startIdx
            fh.seek(cls.fileHeaderSizeInBytes)
            for frameIdx in range(numberOfFrames):
                frameHeaderRaw = fh.read(Frms6Reader.frameHeaderSizeInBytes)
                frameHeaderItems = cls.frameHeaderStruct.unpack(frameHeaderRaw)

                # Stash contents of the individual frame header in the
                # respective list
                frameStart.append(frameHeaderItems[0])
                frameInfo.append(frameHeaderItems[1])
                frameId.append(frameHeaderItems[2])
                frameHeight.append(frameHeaderItems[3])
                frameTvSec.append(frameHeaderItems[4])
                frameTvUsec.append(frameHeaderItems[5])
                frameIndex.append(frameHeaderItems[6])
                frameTemp.append(frameHeaderItems[7])
                frameMaxHeight.append(frameHeaderItems[8])

                # Jump to byte after the frame contents
                fh.seek(
                    frameSizeInBytes,
                    1  # force seek relative to the current position
                )

        return {
           "start": frameStart,
           "info": frameInfo,
           "id": frameId,
           "height": frameHeight,
           "tv_sec": frameTvSec,
           "tv_usec": frameTvUsec,
           "index": frameIndex,
           "temp": frameTemp,
           "maxHeight": frameMaxHeight
        }
    
    @classmethod
    def readData(cls, fn, *args, image_range, **kwargs):
        """ Reads chunks of data from a frm6 file. Compatible with ChunkedReader

        Args:
            fn (str): fully qualified file name
            image_range: 2-tuple [start_idx, end_idx[ defining the
                range of frames that ought to be read
            kwargs: the following additional parameters **must** be given:

                * pixels_x (int): number of pixels along x-axis
                * pixels_y (int): number of pixels along y-axis

        Returns:
            numpy.ndarray: Data read from the frm6 file (dtype: uint16)

        """

        # ChunkedReader provides image range..
        startIdx, endIdx = image_range
        numberOfFrames = endIdx - startIdx
        # ..and user must provide image format
        # TODO: pixels_(x/y) Must be provided!
        pixelsX = kwargs.get("pixels_x", None)
        pixelsY = kwargs.get("pixels_y", None)

        # We already know the format of the file header and the frame
        # header (see above), but we have yet to declare the format of the
        # frames. h -> short
        frameSizeInBytes = cls.getFrameSizeInBytes(pixelsX, pixelsY)

        # When reading the file, we'll jump directly to the frame startIdx
        offset = cls.fileHeaderSizeInBytes
        offset += startIdx * (
            cls.frameHeaderSizeInBytes + frameSizeInBytes
        )

        # chunk will record the frames retrieved from file
        # TODO: Check indexing in pyDetLib
        # chunk = np.zeros(
        #     (pixelsY, pixelsX, numberOfFrames),
        #     np.uint16
        # )
        chunk = np.zeros(
            (pixelsX, pixelsY, numberOfFrames),
            np.uint16
        )

        #
        # Seek & read, each chunks re-opens file
        #
        # Entering the context manager opens the file
        with open(fn, 'rb') as fh:
            # Jump to the byte after the file header (and
            # any frames that might already have been read)
            fh.seek(offset)
            for frameIdx in range(numberOfFrames):
                # Jump to byte after the frame header
                fh.seek(
                    cls.frameHeaderSizeInBytes,
                    1  # force seek relative to the current position
                )
                # Read from file handle. Note: contents of the frame
                # are given as unsigned 16 bit integers
                currentFrame = np.frombuffer(
                    fh.read(frameSizeInBytes),
                    np.uint16
                )
                # Since the currentFrame data is flat, we must re-shape.
                # Numpy defaults to C-order (aka row-major aka index WITHIN
                # a row aka last index changes fastest). In the reshape,
                # the newshape must have the slow index aka column-index aka
                # y-index first. However..
                currentFrame = currentFrame.reshape((pixelsY, pixelsX))
                # ..this means that currentFrame.shape = (pixelsY, pixelsX),
                # while the convention in pyDetLib is (pixelsX, pixelsY). I.e.
                # if you want to select the first row in a pyDetLib data set
                # one does: data[:, 0] and NOT how numpy encourages by using
                # C-order: data[0, :].
                chunk[:, :, frameIdx] = np.transpose(currentFrame)
                # FYI: The same is achieved by using
                # currentFrame = np.reshape(
                #     currentFrame,        # Flat currentFrame data
                #     (pixelsX, pixelsY),  # Expected shape (width, height)
                #     order='F'            # Use fortran order (column-first)
                # )

        return chunk
    
    @classmethod
    def getFileHeader(cls, fn):
        """ Returns the file header associated with a frm6 file.

        Args:
            fn (str): fully qualified file name

        Returns:
            OrderedDict: Contents of the file header

        """
        with open(fn, 'rb') as fh:
            # Only read the header portion of the file
            fileHeaderRaw = fh.read(cls.fileHeaderSizeInBytes)
            # Intepret binary data as described above
            fileHeaderItems = cls.fileHeaderStruct.unpack(fileHeaderRaw)
            # Collect in OrderedDictionary
            fileHeaderDict = OrderedDict([
                ("fileHeaderSize", fileHeaderItems[0]),
                ("frameHeaderSize", fileHeaderItems[1]),
                ("nCCDs", fileHeaderItems[2]),
                ("maxWidth", fileHeaderItems[3]),
                ("maxHeight", fileHeaderItems[4]),
                ("version", fileHeaderItems[5]),
                ("dataSetId", fileHeaderItems[6].rstrip(b'\x00')),
                ("width", fileHeaderItems[7]),
                ("height", fileHeaderItems[8])
            ])
        return fileHeaderDict
    
    @classmethod
    def getDataShape(cls, fn, path=None):
        """ Returns the size of the set of image in the given file,
        numpy.shape style.

        Args:
            fn (str): fully qualified file name
            path (str = '/stream', optional): Unused, added for compatibility

        Returns:
            3-tuple: Height & width of the frame and number of frames in the file

        """
        # Get file header and ..
        fileHeader = cls.getFileHeader(fn)
        # .. retrieve frame width and height
        frameWidth = int(fileHeader['width'])
        frameHeight = int(fileHeader['height'])
        # Now we can calculate the size of frame and frame header (in bytes)
        frameAndHeaderSizeInBytes = cls.frameHeaderSizeInBytes
        frameAndHeaderSizeInBytes += cls.getFrameSizeInBytes(frameWidth, frameHeight)
        # Finally get the whole file size (in bytes, again)
        fileSize = os.path.getsize(fn)
        # Do the math ..
        numberOfFrames = (
            (fileSize - cls.fileHeaderSizeInBytes) / frameAndHeaderSizeInBytes
        )
        # .. and verify that the number of frames is integer!
        if not float(numberOfFrames).is_integer():
            raise Warning('read_frames -- Number of frames is not integer!')
        else:
            numberOfFrames = int(numberOfFrames)

        return (frameWidth, frameHeight, numberOfFrames)
    
def readData(filename, path='/stream', **kwargs):
    """ Reads data from a given file (family) and output reordered images
    in stacks
    
    Args:
        filename (str): the file path and name. If the file is actually a
            family of files only the first file, i.e. the one with index
            00000.h5 should be given.
        path (str = '/stream', optional): the path in the hdf5 file at which the data is
            located.
        kwargs: the following additional parameters may be given:
            
            * image_range ([low, high]): a range of images to be read
            * x_range ([low, high]): a range of pixels to be read
            * y_range ([low, high]): a range of pixels to be read
            * pixels_x (int): number of pixels along x-axis, **compatibility only**.
            * pixels_y (int): number of pixels along y-axis, **compatibility only**.
        
        
    Returns:
        numpy.array: a reordered and inverted image with rank 2
        
    Note:
        This function is compatible with  xfelpycaltools.ChunkedReader
            
    
    """

    imageRange = kwargs.get("image_range", None)
    pixelXRange = kwargs.get("x_range", None)
    pixelYRange = kwargs.get("y_range", None)
    pixelsX = kwargs.get("pixels_x", None)
    pixelsY = kwargs.get("pixels_y", None)
    simulated = kwargs.get("simulated", False)

    f = None
    if filename.find("00000") != -1:
        filenameFam = filename.replace("00000", "%05d")

        f = h5py.File(filenameFam, "r", driver='family',
                      memb_size=20 * 1024 ** 3)  # 20GB chunks
    else:
        f = h5py.File(filename, "r")

    din = None
    if imageRange == None:
        din = f[path]
    else:
        if not simulated:
            din = f[path][:, :, imageRange[0]:imageRange[1]]
        else:
            din = f[path][imageRange[0]:imageRange[1], :, :]

    if simulated:
        din = np.squeeze(din)
        din = np.rollaxis(din, 2)
        din = np.rollaxis(din, 2)
        din = np.rollaxis(din, 1)

        din = np.ascontiguousarray(din)

    d = None
    if pixelXRange == None and pixelYRange == None:
        d = np.array(din[:, :,:])
    else:
        d = np.array(
            din[pixelXRange[0]:pixelXRange[1], pixelYRange[0]:pixelYRange[1],:])
    f.close()
    return np.asarray(d, np.float64)

def getDataSize(filename, path='/stream'):
    """ Returns the number of image in a given file (family)
    
    Args:
        filename (str): the file path and name. If the file is actually a family
            of files only the first file, i.e. the one with index 00000.h5
            should be given.
        path (str = '/stream', optional): the path in the hdf5 file at which
            the data is located.
    
    """

    f = None
    if filename.find("00000") != -1:
        filenameFam = filename.replace("00000", "%05d")
        # print filenameFam
        f = h5py.File(filenameFam, "r", driver='family',
                      memb_size=20 * 1024 ** 3)  # 20GB chunks
    else:
        f = h5py.File(filename, "r")

    return f[path].shape
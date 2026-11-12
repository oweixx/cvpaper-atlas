"""Auditable, multi-label title taxonomy. Same evidence is used for every venue."""
import re

TAXONOMY = {
    'Detection & Segmentation': {
        'Object detection': r'object detect|pedestrian detect|small.object detect|detr\b|\byolo',
        'Segmentation': r'segment|panoptic|instance mask',
        'Scene understanding': r'scene (understanding|graph|parsing)|visual relationship|semantic (understanding|parsing)',
    },
    '3D Vision': {
        'Depth & stereo': r'\bdepth\b|\bstereo\b',
        '3D geometry & reconstruction': r'\b[34]d\b|multi.view|structure.from.motion|\bslam\b|odometry|camera (pose|calibration)',
        'Point clouds & meshes': r'point cloud|point set|\bmesh\w*\b|\blidar\b',
        'Neural rendering': r'\bnerf\b|radiance field|gaussian splatt|neural render|novel.view synthesis',
    },
    'Vision & Language': {
        'Vision-language models': r'vision.language|\bvlm\w*\b|multimodal|multi.modal|image.text|visual.language',
        'Captioning, VQA & grounding': r'caption|visual question|\bvqa\b|visual grounding|referring expression',
    },
    'Image & Video Generation': {
        'Diffusion models': r'diffusion|flow.matching|rectified.flow',
        'Image & video synthesis': r'generativ|\bgans?\b|image synthesis|video synthesis|text.to.image|text.to.video',
        'Editing & inpainting': r'image.edit|video.edit|inpaint|outpaint|style transfer',
    },
    'Video & Motion': {
        'Tracking': r'track',
        'Video & action understanding': r'video|action (recognition|detect|localiz)|temporal (action|localiz)',
        'Optical flow & motion': r'optical flow|motion (estimat|predict|segment|capture)',
    },
    'Recognition & Representation': {
        'Recognition & classification': r'classification|recognition|fine.grained',
        'Self-supervised representations': r'self.supervis|contrastive|representation learn|masked (image|autoencod)',
        'Few-shot & zero-shot learning': r'few.shot|zero.shot|open.vocabulary|open.world|open.set',
        'Retrieval & matching': r'retrieval|image match|feature match|correspondence|re.identification',
    },
    'Low-level Vision': {
        'Image restoration': r'denois|deblur|restoration|dehaz|derain|low.light|image enhancement',
        'Super-resolution': r'super.resolution|upsampl',
        'Compression & imaging': r'compression|colorization|demosaic|computational imaging|hyperspectral',
    },
    'People & Faces': {
        'Human pose & bodies': r'human|\bpose\b|\bbody\b|\bhand\b|gesture|avatar|pedestrian',
        'Faces & biometrics': r'\bface\b|facial|biometric|\bgait\b',
    },
    'Robustness & Learning': {
        'Robustness & uncertainty': r'adversarial|robust|uncertainty|out.of.distribution|anomaly|calibrat',
        'Domain adaptation': r'domain.adapt|domain.general|cross.domain|test.time adapt',
        'Continual & federated learning': r'continual|lifelong|incremental learn|federated|unlearning',
        'Efficient models': r'pruning|quantization|distillation|efficient|lightweight|compression',
    },
    'Medical & Scientific Vision': {
        'Medical imaging': r'medical|biomedical|microscopy|histopath|radiology|\bmri\b|tomography|pathology|retinal',
        'Remote sensing': r'remote.sensing|satellite|aerial|earth observation',
    },
}
PATTERNS = {group: {name: re.compile(pattern, re.I) for name, pattern in items.items()} for group, items in TAXONOMY.items()}
TOPICS = list(TAXONOMY)
SUBTOPICS = [topic for items in TAXONOMY.values() for topic in items]


def classify(title):
    areas, details = [], []
    for group, patterns in PATTERNS.items():
        matched = [name for name, pattern in patterns.items() if pattern.search(title)]
        if matched:
            areas.append(group)
            details.extend(matched)
    return areas or ['Other / Unclassified'], details or ['Other / Unclassified']

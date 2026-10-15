import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import Player from '@/components/Player';
import Subtitle from '@/components/Subtitle';
import Keypoints from '@/components/Keypoints';
import SummaryView from '@/components/Summary';
import MindmapView from '@/components/Mindmap';
import { listTranscripts, listKeypoints, getSummary, getMindmap } from '@/api';
import type { Transcript, Keypoint, Summary, Mindmap } from '@/types';

export default function CourseDetail() {
  const { id } = useParams<{ id: string }>();
  const courseId = Number(id);
  const [currentSec, setCurrentSec] = useState(0);
  const [transcripts, setTranscripts] = useState<Transcript[]>([]);
  const [keypoints, setKeypoints] = useState<Keypoint[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [mindmap, setMindmap] = useState<Mindmap | null>(null);

  useEffect(() => {
    listTranscripts(courseId).then(setTranscripts).catch(() => {});
    listKeypoints(courseId).then(setKeypoints).catch(() => {});
    getSummary(courseId).then(setSummary).catch(() => {});
    getMindmap(courseId).then(setMindmap).catch(() => {});
  }, [courseId]);

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2 space-y-3">
        <Player src="" onTimeUpdate={setCurrentSec} />
        <Subtitle transcripts={transcripts} currentSec={currentSec} />
      </div>
      <div className="space-y-3">
        <Keypoints keypoints={keypoints} />
        {summary && <SummaryView summary={summary} />}
        {mindmap && <MindmapView mindmap={mindmap} />}
      </div>
    </div>
  );
}